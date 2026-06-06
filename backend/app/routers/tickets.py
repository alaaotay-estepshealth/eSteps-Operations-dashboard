import json
from typing import Optional, Set
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin, require_operator
from app.config import settings
from app.database import get_db
from app.models.ai_suggestion import AISuggestion
from app.models.audit_log import AuditLog
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.responses import (
    PaginatedSuggestions,
    PaginatedTickets,
    SuggestionDetail,
    TicketCategoryBreakdown,
    TicketRow,
    TicketStats,
    TicketStatusUpdate,
)
from app.services.audit import write_audit
from app.services.gemini import (
    GEMINI_MODEL,
    call_gemini,
    cost_per_call_usd,
    gemini_today_spend_usd,
    record_decision_row,
)

router = APIRouter(prefix="/admin/tickets", tags=["tickets"])


@router.get("/stats", response_model=TicketStats)
def get_ticket_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    open_count = db.query(func.count(Ticket.id)).filter(Ticket.status == "open").scalar() or 0
    in_progress = db.query(func.count(Ticket.id)).filter(Ticket.status == "in_progress").scalar() or 0
    resolved = db.query(func.count(Ticket.id)).filter(Ticket.status == "resolved").scalar() or 0
    total = open_count + in_progress + resolved

    avg_response = db.query(func.avg(Ticket.response_time_min)).filter(
        Ticket.response_time_min.isnot(None)
    ).scalar()
    avg_confidence = db.query(func.avg(Ticket.ai_confidence)).scalar() or 0
    verified_count = db.query(func.count(Ticket.id)).filter(Ticket.human_verified.is_(True)).scalar() or 0

    cat_rows = db.query(
        Ticket.ai_category,
        func.count(Ticket.id),
        func.avg(Ticket.ai_priority_score),
        func.avg(Ticket.ai_confidence),
    ).group_by(Ticket.ai_category).all()

    categories = [
        TicketCategoryBreakdown(
            category=c, count=cnt,
            avg_priority=round(float(p), 1),
            avg_confidence=round(float(conf), 3),
        )
        for c, cnt, p, conf in cat_rows
    ]

    return TicketStats(
        open_count=open_count,
        in_progress_count=in_progress,
        resolved_count=resolved,
        avg_response_time_min=round(float(avg_response), 1) if avg_response else None,
        avg_ai_confidence=round(float(avg_confidence), 3),
        human_verification_rate_pct=round(verified_count / max(total, 1) * 100, 1),
        categories=categories,
    )


@router.get("", response_model=PaginatedTickets)
def list_tickets(
    status: Optional[str] = Query(None),
    ai_category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PaginatedTickets:
    filters = []
    params: dict = {"limit": limit, "offset": offset}
    if status:
        filters.append("t.status = :status")
        params["status"] = status
    if ai_category:
        filters.append("t.ai_category = :ai_category")
        params["ai_category"] = ai_category
    where = "WHERE " + " AND ".join(filters) if filters else ""

    total = db.execute(
        text(f"SELECT count(*) FROM tickets t {where}"), params
    ).scalar() or 0

    rows = db.execute(
        text(
            "SELECT t.id, t.source, t.subject, t.body_preview, t.ai_category, "
            "t.ai_priority_score, t.ai_confidence, t.assigned_to, t.status, "
            "t.human_verified, t.human_override, t.created_at, t.resolved_at, "
            "t.response_time_min, "
            "s.id AS s_id, s.entity_type AS s_entity_type, "
            "s.entity_id AS s_entity_id, s.payload AS s_payload, "
            "s.applied_payload AS s_applied_payload, s.model AS s_model, "
            "s.confidence AS s_confidence, s.status AS s_status, "
            "s.rationale AS s_rationale, s.applied_at AS s_applied_at, "
            "s.applied_by AS s_applied_by, s.rejected_at AS s_rejected_at, "
            "s.rejected_by AS s_rejected_by, "
            "s.rejection_reason AS s_rejection_reason, "
            "s.ai_request_id AS s_ai_request_id, "
            "s.created_at AS s_created_at, s.updated_at AS s_updated_at "
            "FROM tickets t "
            "LEFT JOIN LATERAL ("
            "  SELECT * FROM ai_suggestions "
            "  WHERE entity_type='ticket' AND entity_id = t.id "
            "    AND status != 'superseded' "
            "  ORDER BY created_at DESC LIMIT 1"
            ") s ON true "
            f"{where} "
            "ORDER BY t.created_at DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings().all()

    tickets_out: list[TicketRow] = []
    for r in rows:
        suggestion = None
        if r["s_id"] is not None:
            suggestion = SuggestionDetail(
                id=r["s_id"],
                entity_type=r["s_entity_type"],
                entity_id=r["s_entity_id"],
                payload=r["s_payload"] or {},
                applied_payload=r["s_applied_payload"],
                model=r["s_model"],
                confidence=r["s_confidence"],
                status=r["s_status"],
                rationale=r["s_rationale"],
                applied_at=r["s_applied_at"],
                applied_by=r["s_applied_by"],
                rejected_at=r["s_rejected_at"],
                rejected_by=r["s_rejected_by"],
                rejection_reason=r["s_rejection_reason"],
                ai_request_id=r["s_ai_request_id"],
                created_at=r["s_created_at"],
                updated_at=r["s_updated_at"],
            )
        tickets_out.append(
            TicketRow(
                id=r["id"],
                created_at=r["created_at"],
                source=r["source"],
                subject=r["subject"],
                body_preview=r["body_preview"],
                ai_category=r["ai_category"],
                ai_priority_score=r["ai_priority_score"],
                ai_confidence=r["ai_confidence"],
                assigned_to=r["assigned_to"],
                status=r["status"],
                resolved_at=r["resolved_at"],
                response_time_min=r["response_time_min"],
                human_verified=r["human_verified"],
                human_override=r["human_override"],
                suggestion=suggestion,
            )
        )

    return PaginatedTickets(
        total=total,
        limit=limit,
        offset=offset,
        tickets=tickets_out,
    )


@router.patch("/{ticket_id}/status")
def update_ticket_status(
    ticket_id: str,
    update: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = update.status
    if update.assigned_to:
        ticket.assigned_to = update.assigned_to
    db.commit()

    db.add(AuditLog(
        level="INFO",
        source="admin_dashboard",
        message=f"Ticket status updated to {update.status} by {current_user.username}",
        entity_id=ticket.id,
        entity_type="ticket",
        user_id=current_user.username,
    ))
    db.commit()

    return {"status": "updated", "ticket_id": ticket_id}


# ─── AI Triage (ES-OPS-09 Task 6) ───────────────────────────────────────────

_VALID_CATEGORIES = {"billing", "technical", "partnership", "support"}

_TRIAGE_INSTRUCTION = (
    "You are a triage AI for the eSteps Health operations team. "
    "Classify this incoming support ticket.\n\n"
    "TICKET\n"
    "  Source:  {source}\n"
    "  Subject: {subject}\n"
    "  Body:    {body}\n\n"
    "Available operator usernames (for assigned_to): {operators_csv}\n\n"
    "Return ONLY a JSON object with these exact fields, no markdown fence, "
    "no prose around it:\n"
    "{{\n"
    '  "category":       "billing" | "technical" | "partnership" | "support",\n'
    '  "priority_score": <integer 1-5, where 5 = urgent>,\n'
    '  "assigned_to":    "<one of the operator usernames above>" | null,\n'
    '  "rationale":      "<1-2 sentences explaining your reasoning>",\n'
    '  "confidence":     <float 0.0-1.0, how unambiguous the signals are>\n'
    "}}\n\n"
    "Rules:\n"
    "- legal/refund/chargeback/data-deletion/GDPR -> category=billing, priority>=4\n"
    "- error/bug/crash/500/integration/API failure -> category=technical\n"
    "- partnership/research/collaboration/grant/IRB -> category=partnership\n"
    "- otherwise -> category=support\n"
    "- urgent/down/blocking/payment-failed -> priority_score=5\n"
    "- ambiguous body -> confidence<0.7, assigned_to=null"
)


def _available_operators(db: Session) -> Set[str]:
    rows = db.execute(
        text(
            "SELECT username FROM users "
            "WHERE role IN ('admin','operator') AND is_active = true"
        )
    ).all()
    return {r[0] for r in rows}


def _build_triage_prompt(ticket, operators: Set[str]) -> str:
    return _TRIAGE_INSTRUCTION.format(
        source=ticket.source or "—",
        subject=(ticket.subject or "")[:200],
        body=(ticket.body_preview or "")[:1000],
        operators_csv=", ".join(sorted(operators)) or "(none configured)",
    )


def _parse_and_validate_triage(raw: str, operators: Set[str]) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1].lstrip("json").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502, detail=f"Gemini returned malformed JSON: {e}"
        )

    if data.get("category") not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=502, detail=f"Invalid category: {str(data.get('category'))[:40]!r}"
        )
    pri = data.get("priority_score")
    if not isinstance(pri, int) or not 1 <= pri <= 5:
        raise HTTPException(
            status_code=502, detail=f"Invalid priority_score: {pri!r}"
        )
    rationale = (data.get("rationale") or "").strip()
    if not rationale:
        raise HTTPException(status_code=502, detail="Missing rationale")

    assignee = data.get("assigned_to")
    if assignee and assignee not in operators:
        assignee = None

    conf = data.get("confidence")
    if not isinstance(conf, (int, float)) or not 0.0 <= float(conf) <= 1.0:
        conf = None

    return {
        "category": data["category"],
        "priority_score": pri,
        "assigned_to": assignee,
        "rationale": rationale,
        "confidence": float(conf) if conf is not None else None,
    }


@router.post("/{ticket_id}/ai-triage", response_model=SuggestionDetail)
def triage_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_operator),
) -> SuggestionDetail:
    ticket = (
        db.query(Ticket)
        .filter(Ticket.id == ticket_id)
        .with_for_update()
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status == "resolved":
        raise HTTPException(status_code=409, detail="Cannot triage resolved ticket")

    if gemini_today_spend_usd(db) >= settings.ai_daily_budget_usd:
        raise HTTPException(
            status_code=503,
            detail="Daily Gemini budget exhausted, retry after midnight UTC",
        )

    # Supersede any existing pending suggestion in the same transaction.
    db.execute(
        text(
            "UPDATE ai_suggestions SET status='superseded', updated_at=now() "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='pending'"
        ),
        {"tid": str(ticket_id)},
    )

    operators = _available_operators(db)
    prompt = _build_triage_prompt(ticket, operators)

    raw = call_gemini(prompt)
    parsed = _parse_and_validate_triage(raw, operators)

    ai_req_id = record_decision_row(
        db,
        request_type="ticket_triage",
        request_payload={"ticket_id": str(ticket_id)},
        response_payload=parsed,
        cost_estimate_usd=cost_per_call_usd(),
        confidence=parsed.get("confidence"),
    )

    suggestion = AISuggestion(
        entity_type="ticket",
        entity_id=ticket_id,
        payload=parsed,
        model=GEMINI_MODEL,
        confidence=parsed.get("confidence"),
        rationale=parsed.get("rationale"),
        ai_request_id=ai_req_id,
        status="pending",
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    write_audit(
        db,
        user,
        action="ai.triage.request",
        resource_type="ticket",
        resource_id=str(ticket_id),
        payload={
            "suggestion_id": str(suggestion.id),
            "confidence": parsed.get("confidence"),
        },
    )

    return SuggestionDetail.model_validate(suggestion, from_attributes=True)


@router.get("/{ticket_id}/suggestions", response_model=PaginatedSuggestions)
def list_ticket_suggestions(
    ticket_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> PaginatedSuggestions:
    q = db.query(AISuggestion).filter(
        AISuggestion.entity_type == "ticket",
        AISuggestion.entity_id == ticket_id,
    )
    total = q.count()
    rows = (
        q.order_by(AISuggestion.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return PaginatedSuggestions(
        total=total,
        limit=limit,
        offset=offset,
        suggestions=[
            SuggestionDetail.model_validate(r, from_attributes=True) for r in rows
        ],
    )
