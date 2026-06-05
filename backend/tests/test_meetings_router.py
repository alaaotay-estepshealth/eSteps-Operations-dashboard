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


def test_patch_notes_updates_prep_and_recap(client, db, leads_db, operator_token, admin_token):
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'P', 'Q')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)
    res = client.patch(
        f"/admin/meetings/{bid}/notes",
        json={"prep_md": "ask about IRB", "recap_md": ""},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res.status_code == 200
    detail = client.get(f"/admin/meetings/{bid}",
                        headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert detail["notes"]["prep_md"] == "ask about IRB"


def test_notes_patch_requires_operator(client, db, leads_db):
    from app.auth import create_access_token
    readonly = create_access_token({"sub": "v", "role": "readonly"})
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'R', 'O')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)
    res = client.patch(f"/admin/meetings/{bid}/notes", json={"prep_md": "nope"},
                       headers={"Authorization": f"Bearer {readonly}"})
    assert res.status_code == 403


def test_task_create_update_delete(client, db, leads_db, operator_token, admin_token):
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'T', 'D')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)

    create = client.post(
        f"/admin/meetings/{bid}/tasks",
        json={"title": "Send case study"},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert create.status_code == 200
    task_id = create.json()["id"]

    upd = client.patch(
        f"/admin/meetings/{bid}/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert upd.status_code == 200
    assert upd.json()["done"] is True
    assert upd.json()["done_at"] is not None

    rem = client.delete(
        f"/admin/meetings/{bid}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert rem.status_code == 200

    detail = client.get(f"/admin/meetings/{bid}",
                        headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert detail["tasks"] == []


def test_task_404_when_wrong_booking(client, db, leads_db, operator_token):
    lid = uuid4()
    leads_db.execute(text("INSERT INTO leads (id, first_name, last_name) VALUES (:id, 'A', 'C')"),
                     {"id": str(lid)})
    leads_db.commit()
    bid = _seed_booking(db, lid)
    create = client.post(f"/admin/meetings/{bid}/tasks", json={"title": "x"},
                         headers={"Authorization": f"Bearer {operator_token}"})
    task_id = create.json()["id"]
    other = uuid4()
    res = client.patch(f"/admin/meetings/{other}/tasks/{task_id}", json={"done": True},
                       headers={"Authorization": f"Bearer {operator_token}"})
    assert res.status_code == 404
