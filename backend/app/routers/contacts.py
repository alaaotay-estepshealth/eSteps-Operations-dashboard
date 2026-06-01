from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_leads_db
from app.models.user import User

router = APIRouter(prefix="/admin/contacts", tags=["contacts"])

_TOUCHES = (
    "(CASE WHEN email1_sent_at IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN email2_sent_at IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN email3_sent_at IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN email4_sent_at IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN email5_sent_at IS NOT NULL THEN 1 ELSE 0 END)"
)
_REPLIED = "EXISTS (SELECT 1 FROM conversations c WHERE c.lead_id = leads.id AND c.direction = 'inbound')"


@router.get("")
def list_contacts(
    hot: bool = False,
    stage: Optional[str] = None,
    research_interest: Optional[str] = None,
    replied: Optional[bool] = None,
    score_min: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    filters = ["email1_sent_at IS NOT NULL"]   # "people we contacted"
    params: dict = {"limit": limit, "offset": offset}
    if hot:
        filters.append("lead_score >= 7")
    if stage:
        filters.append("stage = :stage"); params["stage"] = stage
    if research_interest:
        filters.append("research_interest = :ri"); params["ri"] = research_interest
    if score_min is not None:
        filters.append("lead_score >= :smin"); params["smin"] = score_min
    if search:
        filters.append("(first_name ILIKE :q OR last_name ILIKE :q OR institution ILIKE :q)")
        params["q"] = f"%{search}%"
    if replied is True:
        filters.append(_REPLIED)
    elif replied is False:
        filters.append(f"NOT {_REPLIED}")

    where = "WHERE " + " AND ".join(filters)
    total = db.execute(text(f"SELECT count(*) FROM leads {where}"), params).scalar() or 0
    rows = db.execute(text(
        f"SELECT lead_id, CONCAT(first_name, ' ', last_name) AS name, institution, position, "
        f"lead_score, stage, campaign_tag, last_contacted, next_send_date, "
        f"{_TOUCHES} AS touches_sent, {_REPLIED} AS replied "
        f"FROM leads {where} "
        f"ORDER BY lead_score DESC NULLS LAST, last_contacted DESC NULLS LAST "
        f"LIMIT :limit OFFSET :offset"
    ), params).mappings().all()
    return {"total": total, "offset": offset, "limit": limit, "contacts": [dict(r) for r in rows]}


@router.get("/priority")
def priority_queue(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    """Heuristic 'who to contact today' ranking — score + uncontacted/overdue/channel bonuses."""
    rows = db.execute(text(
        "SELECT lead_id, CONCAT(first_name, ' ', last_name) AS name, institution, position, "
        "lead_score, stage, campaign_tag, next_send_date, "
        "(email1_sent_at IS NOT NULL) AS contacted, "
        "(COALESCE(lead_score, 0) * 10 "
        " + CASE WHEN email1_sent_at IS NULL THEN 25 ELSE 0 END "
        " + CASE WHEN next_send_date < CURRENT_DATE THEN 15 ELSE 0 END "
        " + CASE WHEN linkedin_available IS TRUE THEN 3 ELSE 0 END "
        " + CASE WHEN campaign_tag = 'Priority_A' THEN 5 ELSE 0 END) AS priority "
        "FROM leads "
        "WHERE lead_score >= 6 AND stage NOT IN ('cold', 'dead', 'bounced', 'Cold') "
        "ORDER BY priority DESC, lead_score DESC LIMIT :limit"
    ), {"limit": limit}).mappings().all()

    today = date.today()
    out = []
    for r in rows:
        d = dict(r)
        reasons = [f"score {d['lead_score']}"]
        if not d["contacted"]:
            reasons.append("never contacted")
        elif d["next_send_date"] and d["next_send_date"] < today:
            reasons.append("follow-up overdue")
        if d["campaign_tag"] == "Priority_A":
            reasons.append("Priority A")
        d["reason"] = " · ".join(reasons)
        out.append(d)
    return {"leads": out}


@router.get("/{lead_id}")
def get_contact(
    lead_id: str = Path(...),
    db: Session = Depends(get_leads_db),
    _: User = Depends(get_current_user),
):
    row = db.execute(text(
        "SELECT id, lead_id, CONCAT(first_name, ' ', last_name) AS name, email, institution, "
        "department, position, research_interest, research_area, lead_score, esteps_relevance_score, "
        "stage, campaign_stage, campaign_tag, ab_variant, touch_number, last_contacted, next_send_date, "
        "linkedin_url, h_index, publication_count, meeting_scheduled_for, meeting_booked_at, notes, "
        "email1_sent_at, email2_sent_at, email3_sent_at, email4_sent_at, email5_sent_at "
        "FROM leads WHERE lead_id = :lid"
    ), {"lid": lead_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    lead = dict(row)
    lead_uuid = lead.pop("id")
    events = []

    for n in (1, 2, 3, 4, 5):
        ts = lead.get(f"email{n}_sent_at")
        if ts:
            events.append({"type": "email_sent", "label": f"Email {n} sent", "detail": None, "timestamp": ts})

    try:
        conv = db.execute(text(
            "SELECT created_at, body, direction FROM conversations WHERE lead_id = :uid ORDER BY created_at"
        ), {"uid": lead_uuid}).mappings().all()
        for c in conv:
            inbound = c["direction"] == "inbound"
            events.append({
                "type": "reply" if inbound else "outbound",
                "label": "Reply received" if inbound else "Message sent",
                "detail": (c["body"] or "")[:300],
                "timestamp": c["created_at"],
            })
    except Exception:
        pass

    if lead.get("meeting_scheduled_for"):
        events.append({"type": "meeting", "label": "Meeting scheduled", "detail": None, "timestamp": lead["meeting_scheduled_for"]})
    if lead.get("meeting_booked_at"):
        events.append({"type": "meeting", "label": "Meeting booked", "detail": None, "timestamp": lead["meeting_booked_at"]})

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    for n in (1, 2, 3, 4, 5):
        lead.pop(f"email{n}_sent_at", None)

    return {"lead": lead, "timeline": events}
