"""Auto-draft on first detail open + manual /ai-draft endpoint."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _seed(db, leads_db):
    lid = uuid4()
    leads_db.execute(
        text("INSERT INTO leads (id, first_name, last_name, institution, research_area, "
             "lead_score, stage, bio) VALUES (:id, 'Jane', 'Elder', 'Mayo', 'Cardiology', 9.0, "
             "'pitching', 'Cardiology research, IRB-approved studies')"),
        {"id": str(lid)},
    )
    leads_db.commit()
    bid = uuid4()
    db.execute(
        text("INSERT INTO bookings (id, lead_id, status, scheduled_for, duration_min) "
             "VALUES (:id, :lid, 'scheduled', :when, 20)"),
        {"id": str(bid), "lid": str(lid),
         "when": datetime.now(timezone.utc) + timedelta(hours=6)},
    )
    db.commit()
    return bid


def test_first_detail_open_autodrafts_prep(monkeypatch, client, db, leads_db, admin_token):
    bid = _seed(db, leads_db)
    monkeypatch.setattr(
        "app.routers.meetings.call_gemini",
        lambda prompt, timeout=30.0: "## Why this lead matters\nStrong cardiology fit.",
    )
    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    body = res.json()
    assert "Why this lead matters" in body["notes"]["prep_md"]
    assert body["notes"]["ai_drafted_at"] is not None
    assert body["notes"]["ai_model"] == "gemini-2.5-flash"


def test_second_open_does_not_redraft(monkeypatch, client, db, leads_db, admin_token):
    bid = _seed(db, leads_db)
    calls = {"n": 0}

    def fake(prompt, timeout=30.0):
        calls["n"] += 1
        return "draft once"

    monkeypatch.setattr("app.routers.meetings.call_gemini", fake)
    client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert calls["n"] == 1


def test_gemini_5xx_skips_draft_gracefully(monkeypatch, client, db, leads_db, admin_token):
    from fastapi import HTTPException

    def boom(prompt, timeout=30.0):
        raise HTTPException(status_code=502, detail="Gemini upstream returned 503")

    monkeypatch.setattr("app.routers.meetings.call_gemini", boom)
    bid = _seed(db, leads_db)
    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    notes = res.json()["notes"]
    assert notes["prep_md"] == ""
    assert notes["ai_skipped"] == "upstream_error"


def test_budget_exhausted_skips_draft(monkeypatch, client, db, leads_db, admin_token):
    monkeypatch.setattr("app.routers.meetings.gemini_today_spend_usd", lambda db_: 999.0)
    monkeypatch.setattr("app.routers.meetings.call_gemini",
                        lambda *a, **kw: pytest.fail("should not be called"))
    bid = _seed(db, leads_db)
    res = client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert res.json()["notes"]["ai_skipped"] == "budget_exhausted"


def test_force_ai_draft_overrides(monkeypatch, client, db, leads_db, admin_token, operator_token):
    bid = _seed(db, leads_db)
    monkeypatch.setattr("app.routers.meetings.call_gemini", lambda *a, **kw: "first draft")
    client.get(f"/admin/meetings/{bid}", headers={"Authorization": f"Bearer {admin_token}"})

    monkeypatch.setattr("app.routers.meetings.call_gemini", lambda *a, **kw: "second draft")
    # operator can re-draft (without force) only when existing note allows; with force needs admin
    res = client.post(
        f"/admin/meetings/{bid}/ai-draft",
        json={"force": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert "second draft" in res.json()["prep_md"]
