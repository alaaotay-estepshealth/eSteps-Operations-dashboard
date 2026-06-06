"""Shared Gemini 2.5 Flash client + daily-spend tracker.

Two callers today: routers/insights.py (memo + assistant) and
routers/meetings.py (prep auto-draft). Centralizing keeps the upstream
error handling identical and lets us share the daily-spend cache.
"""

import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

GEMINI_MODEL = "gemini-2.5-flash"
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# Soft per-call cost estimate (used until we wire real cost back from Gemini).
# Flash pricing approx $0.075 / 1M in + $0.30 / 1M out — we treat each call as
# ~1500 tokens combined ≈ $0.0006. Conservative enough for the budget guard.
_COST_PER_CALL_USD = 0.0006

# In-process cache for ai_today_spend so a meeting open doesn't query
# ai_decisions every time.
_spend_cache: dict = {"value": 0.0, "expires_at": 0.0}
_SPEND_CACHE_TTL_SEC = 60


def call_gemini(prompt: str, timeout: float = 30.0) -> str:
    """Single Gemini round-trip. Raises HTTPException on failure (caller decides)."""
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY not configured — add it to backend/.env.",
        )
    try:
        resp = httpx.post(
            _GEMINI_URL,
            params={"key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except httpx.HTTPStatusError as e:
        upstream = ""
        try:
            err_json = e.response.json()
            upstream = err_json.get("error", {}).get("message", "")[:200]
        except Exception:
            upstream = (e.response.text or "")[:200]
        hint = ""
        if e.response.status_code in (401, 403):
            hint = " — check GEMINI_API_KEY is valid"
        elif e.response.status_code == 404:
            hint = f" — model '{GEMINI_MODEL}' not available on this key"
        elif e.response.status_code == 429:
            hint = " — quota exceeded; wait or upgrade plan"
        raise HTTPException(
            status_code=502,
            detail=f"Gemini upstream returned {e.response.status_code}{hint}. {upstream}".strip(),
        )
    except (KeyError, IndexError):
        raise HTTPException(
            status_code=502, detail="Unexpected response shape from Gemini"
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="AI service unavailable")


def gemini_today_spend_usd(db: Session) -> float:
    """USD spent on Gemini today across all callers (60-s in-process cache).

    Reads from `ai_decisions` if it exists; otherwise returns 0.0. The table
    is created by webhooks/ai-decision; if it doesn't exist yet we silently
    return 0 — guard is intentionally a no-op until the table is in place.
    """
    now = time.time()
    if now < _spend_cache["expires_at"]:
        return _spend_cache["value"]
    try:
        spent = (
            db.execute(
                text(
                    "SELECT COALESCE(SUM(cost_estimate_usd), 0) FROM ai_decisions "
                    "WHERE created_at::date = CURRENT_DATE"
                )
            ).scalar()
            or 0.0
        )
        spent = float(spent)
    except Exception:
        spent = 0.0
    _spend_cache["value"] = spent
    _spend_cache["expires_at"] = now + _SPEND_CACHE_TTL_SEC
    return spent


def cost_per_call_usd() -> float:
    return _COST_PER_CALL_USD


def record_decision_row(
    db: Session,
    *,
    request_type: str,
    request_payload: dict,
    response_payload: dict,
    cost_estimate_usd: float = _COST_PER_CALL_USD,
    confidence: Optional[float] = None,
) -> Optional[str]:
    """Best-effort write to ai_decisions. Silently no-ops if the table is missing.

    Returns the inserted row's id as a string, or None if the write was
    skipped (table missing, transient DB error, etc.). Callers use the
    returned id as a soft FK from ai_suggestions.ai_request_id.
    """
    try:
        row = db.execute(
            text(
                "INSERT INTO ai_decisions "
                "(request_type, request_payload, response_payload, cost_estimate_usd, "
                " confidence, created_at) "
                "VALUES (:rt, :rq::jsonb, :rs::jsonb, :cost, :conf, now()) "
                "RETURNING id"
            ),
            {
                "rt": request_type,
                "rq": _json(request_payload),
                "rs": _json(response_payload),
                "cost": cost_estimate_usd,
                "conf": confidence,
            },
        ).scalar()
        db.commit()
        _spend_cache["expires_at"] = 0.0
        return str(row) if row is not None else None
    except Exception:
        db.rollback()
        return None


def _json(payload: dict) -> str:
    import json

    return json.dumps(payload, default=str)
