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
        import uuid as _uuid

        # Map resource_id to entity_id only if it's a parseable UUID; else leave null.
        try:
            ent_id = _uuid.UUID(resource_id) if resource_id else None
        except (ValueError, TypeError):
            ent_id = None

        row = AuditLog(
            user_id=str(getattr(user, "id", "") or "") or None,
            level="INFO" if status == "success" else "ERROR",
            source=action,  # e.g. "ai.triage.request"
            message=action,  # operator-readable; consider extending if useful
            entity_type=resource_type,
            entity_id=ent_id,
            metadata_=payload or {},
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
