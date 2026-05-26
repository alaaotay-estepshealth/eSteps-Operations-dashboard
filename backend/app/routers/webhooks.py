import hashlib
import hmac
import random
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.ai_request import AIRequest
from app.models.audit_log import AuditLog
from app.models.system import System
from app.models.workflow_execution import WorkflowExecution
from app.schemas.responses import AIDecisionIngest, N8NCallbackPayload

AI_REVIEW_CONFIDENCE_THRESHOLD = 0.70  # below this, route decision to human review

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SIM_WORKFLOWS = [
    ("est-2", "EST-2: Outreach Engine"),
    ("est-3", "EST-3: Reply Handler"),
    ("est-5", "EST-5: Booking Sync"),
    ("wf_chatbot", "WF1: AI Chatbot"),
    ("wf_leads", "WF2: Lead Automation"),
    ("wf_logs", "WF3: Log Monitoring"),
]
SIM_ERRORS = [
    ("Gmail rate limit reached", "rate_limit"),
    ("Supabase timeout", "timeout"),
    ("OpenAI API error: 429", "api_error"),
    ("Webhook delivery failed", "delivery_error"),
]


def _verify_hmac(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.replace("sha256=", ""))


def _log_webhook_security(db: Session, system_id, message: str) -> None:
    db.add(AuditLog(system_id=system_id, level="ERROR", source="webhook", message=message))
    db.commit()


async def _require_valid_signature(
    request: Request, signature: str, secret: str, *, system_id, label: str, db: Session
) -> None:
    """Enforce HMAC on n8n callbacks.

    Dev: skipped so local testing needs no signature. Prod: the signature is
    mandatory — a missing header is rejected, not silently accepted (the old
    `if signature and not dev` guard let unsigned requests through).
    """
    if settings.environment == "development":
        return
    if not signature:
        _log_webhook_security(db, system_id, f"Missing HMAC signature for {label}")
        raise HTTPException(status_code=401, detail="Missing HMAC signature")
    body = await request.body()
    if not _verify_hmac(body, signature, secret):
        _log_webhook_security(db, system_id, f"HMAC mismatch for {label}")
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")


def _resolve_system(slug: str, db: Session) -> System:
    system = db.query(System).filter(System.slug == slug, System.is_active == True).first()
    if not system:
        raise HTTPException(status_code=404, detail=f"Unknown system: {slug}")
    return system


def _record_execution(payload: N8NCallbackPayload, system_id, db: Session) -> WorkflowExecution:
    execution = WorkflowExecution(
        system_id=system_id,
        workflow_id=payload.workflow_id,
        workflow_name=payload.workflow_name,
        execution_id=payload.execution_id,
        status=payload.status,
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        duration_seconds=payload.duration_seconds,
        error_message=payload.error_message,
        error_type=payload.error_type,
        correlation_id=payload.correlation_id,
        metadata_=payload.metadata,
    )
    db.add(execution)

    level = "INFO" if payload.status == "success" else "ERROR"
    db.add(AuditLog(
        system_id=system_id,
        level=level,
        source="n8n",
        message=f"Workflow '{payload.workflow_name}' {payload.status}"
                + (f": {payload.error_message}" if payload.error_message else ""),
        correlation_id=payload.correlation_id,
    ))
    db.commit()
    return execution


def _record_ai_decision(payload: AIDecisionIngest, system_id, db: Session) -> AIRequest:
    conf = payload.confidence_score
    status = payload.status or (
        "pending_review"
        if conf is not None and conf < AI_REVIEW_CONFIDENCE_THRESHOLD
        else "completed"
    )

    ai_output = dict(payload.ai_output or {})
    if payload.decision_id:
        ai_output["_decision_id"] = payload.decision_id

    record = AIRequest(
        system_id=system_id,
        request_type=payload.request_type,
        workflow_source=payload.workflow_source,
        entity_id=payload.entity_id,
        entity_type=payload.entity_type,
        provider=payload.provider,
        model=payload.model,
        tokens_used=payload.tokens_used,
        cost_usd=payload.cost_usd,
        latency_ms=payload.latency_ms,
        input_preview=(payload.input_preview or "")[:200] or None,
        ai_output=ai_output or None,
        confidence_score=conf,
        used_fallback=payload.used_fallback,
        fallback_reason=payload.fallback_reason,
        status=status,
        retention_until=datetime.utcnow() + timedelta(days=90),
    )
    db.add(record)

    db.add(AuditLog(
        system_id=system_id,
        level="INFO",
        source="ai",
        message=f"AI {payload.request_type} via {payload.provider}"
                + (f" (conf {conf:.2f})" if conf is not None else "")
                + (" → review" if status == "pending_review" else ""),
    ))
    db.commit()
    return record


# ─── Per-system webhook (new) ─────────────────────────────────────────────────

@router.post("/{system_slug}")
async def receive_system_callback(
    request: Request,
    payload: N8NCallbackPayload,
    system_slug: str = Path(...),
    x_n8n_signature: str = Header(None),
    db: Session = Depends(get_db),
):
    system = _resolve_system(system_slug, db)
    await _require_valid_signature(
        request, x_n8n_signature, system.webhook_secret,
        system_id=system.id, label=f"system '{system_slug}'", db=db,
    )

    existing = db.query(WorkflowExecution).filter(
        WorkflowExecution.execution_id == payload.execution_id
    ).first()
    if existing:
        return {"status": "duplicate", "message": "Execution already recorded"}

    execution = _record_execution(payload, system.id, db)
    return {"status": "recorded", "execution_id": execution.execution_id}


# ─── AI decision ingest (n8n AI nodes → ops DB) ──────────────────────────────

@router.post("/{system_slug}/ai-decision")
async def receive_ai_decision(
    request: Request,
    payload: AIDecisionIngest,
    system_slug: str = Path(...),
    x_n8n_signature: str = Header(None),
    db: Session = Depends(get_db),
):
    system = _resolve_system(system_slug, db)
    await _require_valid_signature(
        request, x_n8n_signature, system.webhook_secret,
        system_id=system.id, label=f"ai-decision '{system_slug}'", db=db,
    )

    if payload.decision_id:
        existing = db.query(AIRequest).filter(
            AIRequest.ai_output["_decision_id"].astext == payload.decision_id
        ).first()
        if existing:
            return {"status": "duplicate", "id": str(existing.id)}

    record = _record_ai_decision(payload, system.id, db)
    return {"status": "recorded", "id": str(record.id), "review": record.status == "pending_review"}


# ─── Legacy single-system webhook (backward-compatible) ──────────────────────

@router.post("/n8n")
async def receive_n8n_callback(
    request: Request,
    payload: N8NCallbackPayload,
    x_n8n_signature: str = Header(None),
    db: Session = Depends(get_db),
):
    """Backward-compatible endpoint — routes to esteps-leads system."""
    system = _resolve_system("esteps-leads", db)
    await _require_valid_signature(
        request, x_n8n_signature, system.webhook_secret or settings.n8n_webhook_secret,
        system_id=system.id, label="legacy esteps-leads", db=db,
    )

    existing = db.query(WorkflowExecution).filter(
        WorkflowExecution.execution_id == payload.execution_id
    ).first()
    if existing:
        return {"status": "duplicate", "message": "Execution already recorded"}

    execution = _record_execution(payload, system.id, db)
    return {"status": "recorded", "execution_id": execution.execution_id}


# ─── Simulation (dev only) ────────────────────────────────────────────────────

@router.post("/n8n/simulate")
def simulate_n8n(
    count: int = 1,
    failure_rate: float = 0.12,
    db: Session = Depends(get_db),
):
    if settings.environment != "development":
        raise HTTPException(status_code=404, detail="Simulation disabled")

    system = _resolve_system("esteps-leads", db)
    count = max(1, min(count, 25))
    failures = 0
    for _ in range(count):
        wf_id, wf_name = random.choice(SIM_WORKFLOWS)
        failed = random.random() < failure_rate
        duration = round(random.uniform(0.8, 8.5), 2)
        error_message, error_type = (None, None)
        if failed:
            error_message, error_type = random.choice(SIM_ERRORS)
            failures += 1

        payload = N8NCallbackPayload(
            workflow_id=wf_id,
            workflow_name=wf_name,
            execution_id=f"sim_{uuid.uuid4().hex[:12]}",
            status="failed" if failed else "success",
            duration_seconds=duration,
            error_message=error_message,
            error_type=error_type,
            correlation_id=f"corr_{uuid.uuid4().hex[:8]}",
            metadata={"simulated": True},
        )
        _record_execution(payload, system.id, db)

    return {"status": "ok", "count": count, "failures": failures}
