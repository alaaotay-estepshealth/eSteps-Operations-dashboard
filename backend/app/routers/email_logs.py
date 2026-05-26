from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_leads_db
from app.models.user import User
from app.schemas.responses import (
    ABComparison,
    EmailLogRow,
    EmailStats,
    EmailStepMetrics,
    PaginatedEmailLogs,
)

router = APIRouter(prefix="/admin/emails", tags=["email-logs"])

_STEP_COL = {1: "email1_sent_at", 2: "email2_sent_at", 3: "email3_sent_at",
             4: "email4_sent_at", 5: "email5_sent_at"}


@router.get("/stats", response_model=EmailStats)
def get_email_stats(
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    _q = lambda sql: db.execute(text(sql)).scalar() or 0

    step_metrics = []
    total_sent = 0
    total_bounced_global = _q("SELECT COUNT(*) FROM leads WHERE bounce_at IS NOT NULL")

    for step in range(1, 6):
        col = _STEP_COL[step]
        sent = _q(f"SELECT COUNT(*) FROM leads WHERE {col} IS NOT NULL")
        bounced = _q(f"SELECT COUNT(*) FROM leads WHERE {col} IS NOT NULL AND bounce_at IS NOT NULL") if step == 1 else 0
        delivered = sent - bounced
        total_sent += sent
        step_metrics.append(EmailStepMetrics(
            step=step, sent=sent, delivered=delivered, bounced=bounced,
            opened=0, delivery_rate_pct=round(delivered / max(sent, 1) * 100, 1),
            open_rate_pct=0.0,
        ))

    # Supplement with email_logs table open tracking
    el_total = _q("SELECT COUNT(*) FROM email_logs")
    el_opened = _q("SELECT COUNT(*) FROM email_logs WHERE open_detected IS TRUE")
    if el_total > 0:
        for sm in step_metrics:
            step_opened = db.execute(text(
                "SELECT COUNT(*) FROM email_logs WHERE sequence_step = :s AND open_detected IS TRUE"
            ), {"s": sm.step}).scalar() or 0
            sm.opened = step_opened
            sm.open_rate_pct = round(step_opened / max(sm.delivered, 1) * 100, 1)

    total_delivered = total_sent - total_bounced_global
    total_opened = el_opened

    # Replies from conversations table (inbound emails)
    replies = _q("SELECT COUNT(*) FROM conversations WHERE direction = 'inbound'")

    # A/B comparison
    va_sent = _q("SELECT COUNT(*) FROM leads WHERE ab_variant = 'A' AND email1_sent_at IS NOT NULL")
    vb_sent = _q("SELECT COUNT(*) FROM leads WHERE ab_variant = 'B' AND email1_sent_at IS NOT NULL")
    va_replied = db.execute(text(
        "SELECT COUNT(*) FROM conversations c JOIN leads l ON c.lead_id = l.id "
        "WHERE c.direction = 'inbound' AND l.ab_variant = 'A'"
    )).scalar() or 0
    vb_replied = db.execute(text(
        "SELECT COUNT(*) FROM conversations c JOIN leads l ON c.lead_id = l.id "
        "WHERE c.direction = 'inbound' AND l.ab_variant = 'B'"
    )).scalar() or 0
    va_rate = round(va_replied / max(va_sent, 1) * 100, 1)
    vb_rate = round(vb_replied / max(vb_sent, 1) * 100, 1)

    ab = ABComparison(
        variant_a_sent=va_sent, variant_b_sent=vb_sent,
        variant_a_open_rate=va_rate, variant_b_open_rate=vb_rate,
        winner="A" if va_rate > vb_rate else ("B" if vb_rate > va_rate else None),
    ) if (va_sent + vb_sent) > 0 else None

    return EmailStats(
        total_sent=total_sent, total_delivered=total_delivered,
        total_bounced=total_bounced_global, total_opened=total_opened,
        delivery_rate_pct=round(total_delivered / max(total_sent, 1) * 100, 1),
        open_rate_pct=round(total_opened / max(total_delivered, 1) * 100, 1),
        bounce_rate_pct=round(total_bounced_global / max(total_sent, 1) * 100, 1),
        step_metrics=step_metrics, ab_comparison=ab,
    )


@router.get("/logs", response_model=PaginatedEmailLogs)
def get_email_logs(
    status: Optional[str] = Query(None),
    ab_variant: Optional[str] = Query(None),
    sequence_step: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    # Try email_logs table first, fall back to leads-derived data
    el_count = db.execute(text("SELECT COUNT(*) FROM email_logs")).scalar() or 0

    if el_count > 0:
        filters = []
        params: dict = {"limit": limit, "offset": offset}
        if status:
            filters.append("el.email_status = :status")
            params["status"] = status
        if ab_variant:
            filters.append("el.ab_variant = :ab_variant")
            params["ab_variant"] = ab_variant
        if sequence_step is not None:
            filters.append("el.sequence_step = :sequence_step")
            params["sequence_step"] = sequence_step
        where = ("AND " + " AND ".join(filters)) if filters else ""

        total = db.execute(text(
            f"SELECT COUNT(*) FROM email_logs el WHERE 1=1 {where}"
        ), params).scalar() or 0

        rows = db.execute(text(
            f"SELECT el.id, el.sent_at as created_at, el.lead_id, "
            f"CONCAT(l.first_name, ' ', l.last_name) as lead_name, "
            f"el.sequence_step, el.ab_variant, el.email_status, el.open_detected, "
            f"el.sent_at, el.subject, el.email_to "
            f"FROM email_logs el LEFT JOIN leads l ON el.lead_id = l.id "
            f"WHERE 1=1 {where} ORDER BY el.sent_at DESC "
            f"LIMIT :limit OFFSET :offset"
        ), params).mappings().all()

        logs = [
            EmailLogRow(
                id=r["id"], created_at=r["created_at"], lead_id=r["lead_id"],
                lead_name=r["lead_name"], sequence_step=r["sequence_step"],
                ab_variant=r["ab_variant"], email_status=r["email_status"],
                open_detected=r["open_detected"] or False,
                sent_at=r["sent_at"], subject=r["subject"] or r.get("email_to"),
                provider="gmail", bounce_reason=None,
            )
            for r in rows
        ]
        return PaginatedEmailLogs(total=total, offset=offset, limit=limit, logs=logs)

    # Derive from leads table — one row per email step sent
    filters = []
    params = {"limit": limit, "offset": offset}
    step_filter = ""
    if sequence_step is not None:
        col = _STEP_COL.get(sequence_step)
        if col:
            step_filter = f"AND {col} IS NOT NULL"
            if sequence_step:
                filters.append(f"step = {sequence_step}")
    if ab_variant:
        filters.append("l.ab_variant = :ab_variant")
        params["ab_variant"] = ab_variant

    # Build union of all 5 email steps from leads
    unions = []
    for step in range(1, 6):
        col = _STEP_COL[step]
        unions.append(
            f"SELECT l.id, {col} as sent_at, l.id as lead_id, "
            f"CONCAT(l.first_name, ' ', l.last_name) as lead_name, "
            f"{step} as sequence_step, l.ab_variant, "
            f"CASE WHEN l.bounce_at IS NOT NULL AND {step}=1 THEN 'bounced' ELSE 'sent' END as email_status, "
            f"FALSE as open_detected, l.email as subject "
            f"FROM leads l WHERE {col} IS NOT NULL"
        )
    union_sql = " UNION ALL ".join(unions)

    ab_filter = ""
    if ab_variant:
        ab_filter = f"AND ab_variant = '{ab_variant}'"

    total = db.execute(text(
        f"SELECT COUNT(*) FROM ({union_sql}) sub WHERE 1=1 {ab_filter}"
    )).scalar() or 0

    rows = db.execute(text(
        f"SELECT * FROM ({union_sql}) sub WHERE 1=1 {ab_filter} "
        f"ORDER BY sent_at DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()

    logs = [
        EmailLogRow(
            id=r["id"], created_at=r["sent_at"], lead_id=r["lead_id"],
            lead_name=r["lead_name"], sequence_step=r["sequence_step"],
            ab_variant=r["ab_variant"], email_status=r["email_status"],
            open_detected=False, sent_at=r["sent_at"],
            subject=r["subject"], provider="gmail", bounce_reason=None,
        )
        for r in rows
    ]
    return PaginatedEmailLogs(total=total, offset=offset, limit=limit, logs=logs)
