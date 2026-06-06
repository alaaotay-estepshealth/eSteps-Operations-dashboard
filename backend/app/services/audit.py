"""Shared audit_logs writer.

Lifted from routers/meetings.py:_audit so suggestions.py and tickets.py
(triage endpoint) can reuse it without copy-paste. Resource type is now
explicit instead of hardcoded to 'meeting'.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User


def write_audit(
    db: Session,
    user: User,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    payload: Optional[dict] = None,
    status: str = "success",
) -> None:
    """Best-effort write to audit_logs. Silently rolls back on failure.

    Mirrors the original meetings._audit contract: never raises, never
    blocks the caller's main flow.
    """
    try:
        from app.models.audit_log import AuditLog

        row = AuditLog(
            user_id=getattr(user, "id", None),
            action=action,
            resource=resource_type,
            resource_id=str(resource_id),
            changes=payload or {},
            status=status,
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
