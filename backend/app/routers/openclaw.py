from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin, require_operator
from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.system import System
from app.models.user import User

router = APIRouter(prefix="/admin/openclaw", tags=["openclaw"])


class AgentCommand(BaseModel):
    message: str
    name: Optional[str] = "Dashboard"
    timeout_seconds: Optional[int] = 120


class WakeEvent(BaseModel):
    text: str
    mode: Optional[str] = "now"


def _require_config():
    if not settings.openclaw_base_url or not settings.openclaw_hook_token:
        raise HTTPException(
            status_code=503,
            detail="OpenClaw not configured — set OPENCLAW_BASE_URL and OPENCLAW_HOOK_TOKEN in backend/.env "
                   "and enable hooks in OpenClaw (hooks.enabled=true).",
        )


def _headers():
    return {"Authorization": f"Bearer {settings.openclaw_hook_token}", "Content-Type": "application/json"}


def _audit(db: Session, user: User, action: str, detail: str):
    system = db.query(System).filter(System.slug == "esteps-leads").first()
    db.add(AuditLog(
        system_id=system.id if system else None,
        level="INFO",
        source="openclaw",
        message=f"{user.username} {action}: {detail[:200]}",
    ))
    db.commit()


@router.get("/status")
def status(_: User = Depends(require_operator)):
    """Whether the OpenClaw link is configured (no secret leaked)."""
    return {
        "configured": bool(settings.openclaw_base_url and settings.openclaw_hook_token),
        "base_url": settings.openclaw_base_url or None,
    }


@router.post("/agent")
def run_agent(
    cmd: AgentCommand,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Launch an OpenClaw agent turn. ADMIN-ONLY + audited — the agent can act on real systems."""
    _require_config()
    message = (cmd.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message is required")

    _audit(db, user, "launched OpenClaw agent action", message)
    timeout = cmd.timeout_seconds or 120
    try:
        resp = httpx.post(
            f"{settings.openclaw_base_url.rstrip('/')}/hooks/agent",
            headers=_headers(),
            json={"message": message, "name": cmd.name or "Dashboard", "timeoutSeconds": timeout},
            timeout=float(timeout + 10),
        )
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        data = resp.json() if ctype.startswith("application/json") else {"text": resp.text}
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="OpenClaw agent timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenClaw error ({e.response.status_code})")
    except Exception:
        raise HTTPException(status_code=503, detail="OpenClaw unreachable")

    result = (
        data.get("text") or data.get("reply") or data.get("message")
        or data.get("output") if isinstance(data, dict) else None
    )
    return {"result": result or data, "raw": data}


@router.post("/wake")
def wake(
    ev: WakeEvent,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Notify the OpenClaw agent of an event (e.g. an alert) — it decides what to do.
    ADMIN-ONLY per report §IV.4.4: /wake is part of the OpenClaw admin-only bridge."""
    _require_config()
    text = (ev.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")

    _audit(db, user, "sent OpenClaw wake event", text)
    try:
        resp = httpx.post(
            f"{settings.openclaw_base_url.rstrip('/')}/hooks/wake",
            headers=_headers(),
            json={"text": text, "mode": ev.mode or "now"},
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"OpenClaw error ({e.response.status_code})")
    except Exception:
        raise HTTPException(status_code=503, detail="OpenClaw unreachable")

    return {"status": "queued"}
