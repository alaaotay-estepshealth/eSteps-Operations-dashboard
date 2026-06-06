"""Sync upserts bookings idempotently from leads.meeting_scheduled_for."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed_lead(leads_db, *, scheduled_for=None):
    lead_id = uuid4()
    leads_db.execute(
        text(
            "INSERT INTO leads (id, first_name, last_name, institution, stage, "
            "meeting_scheduled_for, meeting_booked_at) "
            "VALUES (:id, 'Test', 'Lead', 'Mayo', 'pitching', :sched, now())"
        ),
        {"id": str(lead_id), "sched": scheduled_for},
    )
    leads_db.commit()
    return lead_id


def test_sync_creates_booking_for_each_lead_with_meeting(
    client, leads_db, db, admin_token
):
    when = datetime.now(timezone.utc) + timedelta(days=2)
    lead_id = _seed_lead(leads_db, scheduled_for=when)

    res = client.post(
        "/admin/meetings/sync",
        json={"source": "manual"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] >= 1

    rows = db.execute(
        text("SELECT id, scheduled_for FROM bookings WHERE lead_id = :lid"),
        {"lid": str(lead_id)},
    ).all()
    assert len(rows) == 1


def test_sync_is_idempotent(client, admin_token, db):
    before = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    client.post(
        "/admin/meetings/sync",
        json={"source": "manual"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    client.post(
        "/admin/meetings/sync",
        json={"source": "manual"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    after = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    assert after == before or after - before <= 1  # at most one fresh row from seed


def test_sync_updates_scheduled_for_within_window_keeps_id(
    client, leads_db, db, admin_token
):
    original = datetime.now(timezone.utc) + timedelta(days=3)
    lead_id = _seed_lead(leads_db, scheduled_for=original)

    client.post(
        "/admin/meetings/sync",
        json={"source": "manual"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    booking_id = db.execute(
        text("SELECT id FROM bookings WHERE lead_id = :lid"),
        {"lid": str(lead_id)},
    ).scalar()

    # Reschedule by 3 minutes (within ±5min window → same row)
    new_when = original + timedelta(minutes=3)
    leads_db.execute(
        text("UPDATE leads SET meeting_scheduled_for = :s WHERE id = :id"),
        {"s": new_when, "id": str(lead_id)},
    )
    leads_db.commit()

    res = client.post(
        "/admin/meetings/sync",
        json={"source": "manual"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    rows = db.execute(
        text("SELECT id, rescheduled_from FROM bookings WHERE lead_id = :lid"),
        {"lid": str(lead_id)},
    ).all()
    assert len(rows) == 1
    assert rows[0][0] == booking_id
    assert rows[0][1] is not None  # rescheduled_from stashed


def test_sync_dry_run_does_not_write(client, leads_db, db, admin_token):
    when = datetime.now(timezone.utc) + timedelta(days=4)
    _seed_lead(leads_db, scheduled_for=when)
    before = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    res = client.post(
        "/admin/meetings/sync",
        json={"source": "manual", "dry_run": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    after = db.execute(text("SELECT count(*) FROM bookings")).scalar()
    assert after == before
    assert res.json()["dry_run"] is True


def test_sync_requires_admin(client, operator_token):
    res = client.post(
        "/admin/meetings/sync",
        json={"source": "manual"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res.status_code == 403
