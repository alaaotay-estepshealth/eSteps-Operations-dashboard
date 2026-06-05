"""List + detail endpoints for meetings."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed_booking(db, lead_id, *, when=None):
    bid = uuid4()
    db.execute(
        text(
            "INSERT INTO bookings (id, lead_id, status, scheduled_for, duration_min) "
            "VALUES (:id, :lid, 'scheduled', :when, 20)"
        ),
        {"id": str(bid), "lid": str(lead_id), "when": when or datetime.now(timezone.utc) + timedelta(hours=4)},
    )
    db.commit()
    return bid


def test_list_returns_paginated_meetings(client, db, leads_db, admin_token):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, institution, stage) "
             "VALUES (:id, 'X', 'Y', 'Mayo', 'pitching')"),
        {"id": str(lid)},
    )
    leads_db.commit()
    _seed_booking(db, lid)

    res = client.get("/admin/meetings", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert any(str(i["lead_id"]) == str(lid) for i in items)


def test_detail_returns_booking_lead_empty_notes(client, db, leads_db, admin_token):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, institution, stage, lead_score) "
             "VALUES (:id, 'A', 'B', 'Stanford', 'pitching', 8.5)"),
        {"id": str(lid)},
    )
    leads_db.commit()
    bid = _seed_booking(db, lid)

    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["booking"]["id"] == str(bid)
    assert body["lead"]["name"] == "A B"
    assert body["tasks"] == []
    assert "prep_md" in body["notes"]


def test_detail_not_found(client, admin_token):
    res = client.get(f"/admin/meetings/{uuid4()}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 404


def test_list_requires_auth(client):
    res = client.get("/admin/meetings")
    assert res.status_code == 401
