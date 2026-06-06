"""Overdue meeting tasks bubble into /admin/followups + briefing counts."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_overdue_meeting_task_appears_in_followups(client, db, leads_db, admin_token):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, stage) "
             "VALUES (:id, 'A', 'B', 'pitching')"),
        {"id": str(lid)},
    )
    leads_db.commit()
    bid = uuid4()
    db.execute(
        text("INSERT INTO bookings (id, lead_id, status, scheduled_for) "
             "VALUES (:id, :lid, 'scheduled', :w)"),
        {"id": str(bid), "lid": str(lid),
         "w": datetime.now(timezone.utc) + timedelta(days=2)},
    )
    db.execute(
        text("INSERT INTO meeting_tasks (id, booking_id, title, due_at) "
             "VALUES (:id, :bid, 'Send PDF', :d)"),
        {"id": str(uuid4()), "bid": str(bid),
         "d": datetime.now(timezone.utc) - timedelta(hours=4)},
    )
    db.commit()

    res = client.get("/admin/followups", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert "open_meeting_tasks" in body
    assert body["open_meeting_tasks"]["count"] >= 1
    titles = [t["title"] for t in body["open_meeting_tasks"]["tasks"]]
    assert "Send PDF" in titles


def test_briefing_includes_meeting_open_tasks(client, db, leads_db, admin_token):
    res = client.get("/admin/briefing", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert "meeting_open_tasks" in body["priorities"]
    assert "meetings_today" in body["priorities"]


def test_calendar_includes_booking_id_and_task_counts(client, admin_token):
    res = client.get("/admin/bookings/calendar",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    meetings = res.json().get("meetings", [])
    if meetings:
        sample = meetings[0]
        assert "booking_id" in sample
        assert "open_task_count" in sample
        assert "has_notes" in sample
