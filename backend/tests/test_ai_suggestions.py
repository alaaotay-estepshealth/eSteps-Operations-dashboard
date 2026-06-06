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
