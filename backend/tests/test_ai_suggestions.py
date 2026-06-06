"""AI suggestion lifecycle tests — triage, apply, reject, read, RBAC, race."""
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed_ticket(db, *, status="open"):
    tid = uuid4()
    db.execute(
        text(
            "INSERT INTO tickets (id, source, subject, body_preview, status) "
            "VALUES (:id, 'email', 'Refund request Q3', "
            "'Hi, I would like a refund for invoice #4521', :st)"
        ),
        {"id": str(tid), "st": status},
    )
    db.commit()
    return tid


def _fake_gemini_ok(prompt, timeout=30.0):
    return json.dumps(
        {
            "category": "billing",
            "priority_score": 4,
            "assigned_to": None,
            "rationale": "Refund language clearly indicates billing concern.",
            "confidence": 0.86,
        }
    )


def _seed_pending_suggestion(db, ticket_id, *, payload=None):
    sid = uuid4()
    payload = payload or {
        "category": "billing",
        "priority_score": 4,
        "assigned_to": None,
        "rationale": "test",
        "confidence": 0.8,
    }
    db.execute(
        text(
            "INSERT INTO ai_suggestions "
            "(id, entity_type, entity_id, payload, model, confidence, status, rationale) "
            "VALUES (:id, 'ticket', :tid, :p::jsonb, 'gemini-2.5-flash', 0.8, 'pending', "
            "'test')"
        ),
        {
            "id": str(sid),
            "tid": str(ticket_id),
            "p": json.dumps(payload),
        },
    )
    db.commit()
    return sid


def test_triage_creates_pending_suggestion(monkeypatch, client, db, admin_token):
    monkeypatch.setattr("app.routers.tickets.call_gemini", _fake_gemini_ok)
    tid = _seed_ticket(db)

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["entity_type"] == "ticket"
    assert body["status"] == "pending"
    assert body["payload"]["category"] == "billing"
    assert body["payload"]["priority_score"] == 4
    assert body["confidence"] == 0.86

    row = db.execute(
        text(
            "SELECT count(*) FROM ai_suggestions "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='pending'"
        ),
        {"tid": str(tid)},
    ).scalar()
    assert row == 1


def test_triage_supersedes_existing_pending(monkeypatch, client, db, admin_token):
    monkeypatch.setattr("app.routers.tickets.call_gemini", _fake_gemini_ok)
    tid = _seed_ticket(db)
    client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    pending = db.execute(
        text(
            "SELECT count(*) FROM ai_suggestions "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='pending'"
        ),
        {"tid": str(tid)},
    ).scalar()
    superseded = db.execute(
        text(
            "SELECT count(*) FROM ai_suggestions "
            "WHERE entity_type='ticket' AND entity_id=:tid AND status='superseded'"
        ),
        {"tid": str(tid)},
    ).scalar()
    assert pending == 1
    assert superseded == 1


def test_triage_parse_error_returns_502(monkeypatch, client, db, admin_token):
    monkeypatch.setattr(
        "app.routers.tickets.call_gemini",
        lambda prompt, timeout=30.0: "not json at all",
    )
    tid = _seed_ticket(db)

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 502
    assert "malformed JSON" in res.text or "Invalid" in res.text

    row = db.execute(
        text("SELECT count(*) FROM ai_suggestions WHERE entity_id=:tid"),
        {"tid": str(tid)},
    ).scalar()
    assert row == 0


def test_triage_resolved_ticket_returns_409(monkeypatch, client, db, admin_token):
    called = {"n": 0}

    def sentinel(prompt, timeout=30.0):
        called["n"] += 1
        return _fake_gemini_ok(prompt)

    monkeypatch.setattr("app.routers.tickets.call_gemini", sentinel)
    tid = _seed_ticket(db, status="resolved")

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 409
    assert called["n"] == 0


def test_triage_requires_operator_403_for_readonly(monkeypatch, client, db):
    from app.auth import create_access_token

    readonly = create_access_token({"sub": "viewer", "role": "readonly"})
    monkeypatch.setattr("app.routers.tickets.call_gemini", _fake_gemini_ok)
    tid = _seed_ticket(db)

    res = client.post(
        f"/admin/tickets/{tid}/ai-triage",
        headers={"Authorization": f"Bearer {readonly}"},
    )
    assert res.status_code == 403


def test_apply_writes_to_ticket_and_marks_verified(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    res = client.post(
        f"/admin/suggestions/{sid}/apply",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "applied"
    assert body["applied_at"] is not None

    ticket_row = db.execute(
        text(
            "SELECT ai_category, ai_priority_score, human_verified, human_override "
            "FROM tickets WHERE id=:tid"
        ),
        {"tid": str(tid)},
    ).mappings().first()
    assert ticket_row["ai_category"] == "billing"
    assert ticket_row["ai_priority_score"] == 4
    assert ticket_row["human_verified"] is True
    assert ticket_row["human_override"] is False


def test_apply_with_override_flips_override_flag(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    override = {
        "category": "support",
        "priority_score": 2,
        "assigned_to": None,
        "rationale": "operator disagrees",
        "confidence": 0.9,
    }
    res = client.post(
        f"/admin/suggestions/{sid}/apply",
        json={"override_payload": override},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert res.json()["applied_payload"]["category"] == "support"

    ticket_row = db.execute(
        text("SELECT ai_category, human_override FROM tickets WHERE id=:tid"),
        {"tid": str(tid)},
    ).mappings().first()
    assert ticket_row["ai_category"] == "support"
    assert ticket_row["human_override"] is True


def test_apply_race_returns_409(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)
    db.execute(
        text(
            "UPDATE ai_suggestions SET status='applied', applied_at=now(), "
            "applied_by='someone-else' WHERE id=:id"
        ),
        {"id": str(sid)},
    )
    db.commit()

    res = client.post(
        f"/admin/suggestions/{sid}/apply",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 409
    assert "already" in res.text.lower()


def test_reject_marks_rejected_with_reason(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    res = client.post(
        f"/admin/suggestions/{sid}/reject",
        json={"reason": "low confidence and stale ticket"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "low confidence and stale ticket"
    assert body["rejected_at"] is not None


def test_pending_lists_only_pending_across_tickets(client, db, admin_token):
    t1 = _seed_ticket(db)
    t2 = _seed_ticket(db)
    _seed_pending_suggestion(db, t1)
    s2 = _seed_pending_suggestion(db, t2)
    db.execute(
        text("UPDATE ai_suggestions SET status='rejected' WHERE id=:id"),
        {"id": str(s2)},
    )
    db.commit()

    res = client.get(
        "/admin/suggestions/pending",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    statuses = {s["status"] for s in body["suggestions"]}
    assert statuses == {"pending"}


def test_ticket_suggestion_history_returns_all_statuses(client, db, admin_token):
    tid = _seed_ticket(db)
    s1 = _seed_pending_suggestion(db, tid)
    s2 = _seed_pending_suggestion(db, tid)
    db.execute(
        text("UPDATE ai_suggestions SET status='superseded' WHERE id=:id"),
        {"id": str(s1)},
    )
    db.commit()

    res = client.get(
        f"/admin/tickets/{tid}/suggestions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    statuses = {s["status"] for s in body["suggestions"]}
    assert statuses == {"pending", "superseded"}


def test_ticket_list_includes_latest_pending_suggestion(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)

    res = client.get(
        "/admin/tickets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    row = next(
        (t for t in res.json()["tickets"] if t["id"] == str(tid)), None
    )
    assert row is not None
    assert row["suggestion"] is not None
    assert row["suggestion"]["id"] == str(sid)
    assert row["suggestion"]["status"] == "pending"


def test_ticket_list_excludes_superseded(client, db, admin_token):
    tid = _seed_ticket(db)
    sid = _seed_pending_suggestion(db, tid)
    db.execute(
        text("UPDATE ai_suggestions SET status='superseded' WHERE id=:id"),
        {"id": str(sid)},
    )
    db.commit()

    res = client.get(
        "/admin/tickets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    row = next(
        (t for t in res.json()["tickets"] if t["id"] == str(tid)), None
    )
    assert row is not None
    assert row["suggestion"] is None
