from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db, get_leads_db
from app.models.ai_request import AIRequest
from app.models.user import User
from app.models.workflow_execution import WorkflowExecution

router = APIRouter(prefix="/admin/briefing", tags=["briefing"])

_ACTIVE = "stage NOT IN ('cold', 'dead', 'bounced', 'Cold')"


@router.get("")
def get_briefing(
    leads_db: Session = Depends(get_leads_db),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    lq = lambda s: leads_db.execute(text(s)).scalar() or 0

    new_contacted = lq("SELECT count(*) FROM leads WHERE email1_sent_at >= now() - interval '24 hours'")
    try:
        new_replies = lq(
            "SELECT count(*) FROM conversations WHERE direction = 'inbound' "
            "AND created_at >= now() - interval '24 hours'"
        )
    except Exception:
        new_replies = 0

    executions = db.query(WorkflowExecution).filter(WorkflowExecution.started_at >= day_ago).count()
    failures = db.query(WorkflowExecution).filter(
        WorkflowExecution.status == "failed", WorkflowExecution.started_at >= day_ago
    ).count()
    new_ai = db.query(AIRequest).filter(AIRequest.created_at >= day_ago).count()

    overdue = lq(f"SELECT count(*) FROM leads WHERE next_send_date < CURRENT_DATE AND {_ACTIVE}")
    due_today = lq(f"SELECT count(*) FROM leads WHERE next_send_date = CURRENT_DATE AND {_ACTIVE}")
    upcoming_meetings = lq("SELECT count(*) FROM leads WHERE meeting_scheduled_for >= now()")
    hot_uncontacted = lq(f"SELECT count(*) FROM leads WHERE lead_score >= 7 AND email1_sent_at IS NULL AND {_ACTIVE}")

    return {
        "generated_at": now.isoformat(),
        "overnight": {
            "window": "24h",
            "new_replies": new_replies,
            "new_contacted": new_contacted,
            "executions": executions,
            "failures": failures,
            "new_ai_decisions": new_ai,
        },
        "priorities": {
            "overdue": overdue,
            "due_today": due_today,
            "upcoming_meetings": upcoming_meetings,
            "hot_uncontacted": hot_uncontacted,
        },
    }
