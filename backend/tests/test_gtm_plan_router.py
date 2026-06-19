import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.gtm_initiative import GtmInitiative
from app.models.ai_request import AIRequest
from app.models.strategy_asset import StrategyAsset
from app.models.user import User


def _seed_corpus(db):
    db.add(StrategyAsset(
        relative_path="GTM-2026-OS/01_STRATEGY.md",
        parent_path="GTM-2026-OS",
        name="01_STRATEGY.md",
        is_folder=False,
        mime_type="text/markdown",
        size_bytes=10,
        content=b"# strategy",
    ))
    db.commit()


def _mock_anthropic(monkeypatch, kpi_targets=None):
    payload = {
        "executive_summary": "ok",
        "kpi_targets": kpi_targets or [
            {"period": "30d", "objective": "PT pilots", "target": 2, "unit": "pilots",
             "rationale": "r", "assignee_label": "Nidhal"}
        ],
        "risk_flags": [],
        "recommended_focus": ["x"],
        "source_files": [{"name": "01_STRATEGY.md", "path": "GTM-2026-OS/01_STRATEGY.md", "tokens": 100}],
    }
    monkeypatch.setattr(
        "app.services.gtm_extractor.call_anthropic",
        MagicMock(return_value={"text": json.dumps(payload),
                                "usage": {"input_tokens": 1000, "output_tokens": 500,
                                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}),
    )


def test_generate_requires_operator(client, readonly_token):
    r = client.post("/admin/insights/gtm-plan/generate",
                    headers={"Authorization": f"Bearer {readonly_token}"})
    assert r.status_code == 403


def test_generate_returns_202(client, operator_token, db, monkeypatch):
    _seed_corpus(db)
    _mock_anthropic(monkeypatch)
    r = client.post("/admin/insights/gtm-plan/generate",
                    headers={"Authorization": f"Bearer {operator_token}"})
    assert r.status_code == 202
    body = r.json()
    assert "execution_id" in body
    assert body["status"] in ("queued", "in_flight")


# ---------------------------------------------------------------------------
# Task 10: GET /admin/insights/gtm-plan
# ---------------------------------------------------------------------------

def test_get_plan_returns_none_when_no_run(client, readonly_token):
    r = client.get("/admin/insights/gtm-plan",
                   headers={"Authorization": f"Bearer {readonly_token}"})
    assert r.status_code == 200
    assert r.json()["status"] == "none"


def test_get_plan_returns_latest(client, operator_token, db, monkeypatch):
    _seed_corpus(db)
    _mock_anthropic(monkeypatch)
    r1 = client.post("/admin/insights/gtm-plan/generate",
                     headers={"Authorization": f"Bearer {operator_token}"})
    assert r1.status_code == 202
    r2 = client.get("/admin/insights/gtm-plan",
                    headers={"Authorization": f"Bearer {operator_token}"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "completed"
    assert body["output"]["executive_summary"] == "ok"
    assert body["age_seconds"] is not None and body["age_seconds"] < 60


# ---------------------------------------------------------------------------
# Task 11: GET /admin/insights/gtm-plan/initiatives
# ---------------------------------------------------------------------------

def test_get_plan_initiatives_lists_latest_run(client, operator_token, db, monkeypatch):
    _seed_corpus(db)
    _mock_anthropic(monkeypatch, kpi_targets=[
        {"period": "30d", "objective": "30d goal", "target": 1, "unit": "u", "rationale": "r", "assignee_label": "Nidhal"},
        {"period": "60d", "objective": "60d goal", "target": 2, "unit": "u", "rationale": "r", "assignee_label": "Alaa"},
    ])
    client.post("/admin/insights/gtm-plan/generate",
                headers={"Authorization": f"Bearer {operator_token}"})
    r = client.get("/admin/insights/gtm-plan/initiatives",
                   headers={"Authorization": f"Bearer {operator_token}"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert set(row["period"] for row in rows) == {"30d", "60d"}


def test_get_plan_initiatives_empty(client, readonly_token):
    r = client.get("/admin/insights/gtm-plan/initiatives",
                   headers={"Authorization": f"Bearer {readonly_token}"})
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Task 12: POST .../initiatives/{id}/apply + /reject
# ---------------------------------------------------------------------------

def test_apply_initiative_flips_status(client, operator_token, db, monkeypatch):
    _seed_corpus(db)
    _mock_anthropic(monkeypatch)
    client.post("/admin/insights/gtm-plan/generate",
                headers={"Authorization": f"Bearer {operator_token}"})
    rows = db.query(GtmInitiative).all()
    target = rows[0]

    r = client.post(f"/admin/insights/gtm-plan/initiatives/{target.id}/apply",
                    headers={"Authorization": f"Bearer {operator_token}"})
    assert r.status_code == 200
    db.refresh(target)
    assert target.status == "applied"
    assert target.applied_at is not None


def test_reject_initiative_flips_status(client, operator_token, db, monkeypatch):
    _seed_corpus(db)
    _mock_anthropic(monkeypatch)
    client.post("/admin/insights/gtm-plan/generate",
                headers={"Authorization": f"Bearer {operator_token}"})
    target = db.query(GtmInitiative).first()

    r = client.post(f"/admin/insights/gtm-plan/initiatives/{target.id}/reject",
                    headers={"Authorization": f"Bearer {operator_token}"})
    assert r.status_code == 200
    db.refresh(target)
    assert target.status == "rejected"


def test_apply_readonly_forbidden(client, readonly_token, db):
    init = GtmInitiative(period="30d", objective_label="x", status="suggested")
    db.add(init); db.commit(); db.refresh(init)
    r = client.post(f"/admin/insights/gtm-plan/initiatives/{init.id}/apply",
                    headers={"Authorization": f"Bearer {readonly_token}"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Task 13: GET /admin/gtm-tasks (RBAC)
# ---------------------------------------------------------------------------

def test_gtm_tasks_admin_sees_all(client, admin_token, operator_token, db):
    _ = operator_token  # trigger fixture
    op = db.query(User).filter(User.username == "test-op").first()
    db.add_all([
        GtmInitiative(period="30d", objective_label="task A", status="suggested",
                      assignee_user_id=op.id, assignee_label="test-op"),
        GtmInitiative(period="60d", objective_label="unassigned task", status="suggested"),
        GtmInitiative(period="60d", objective_label="task C", status="applied",
                      assignee_user_id=op.id, assignee_label="test-op"),
    ])
    db.commit()
    r = client.get("/admin/gtm-tasks",
                   headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3


def test_gtm_tasks_operator_sees_own_only(client, operator_token, db):
    client.get("/admin/gtm-tasks", headers={"Authorization": f"Bearer {operator_token}"})
    op = db.query(User).filter(User.username == "test-op").first()
    db.add_all([
        GtmInitiative(period="30d", objective_label="mine", status="suggested",
                      assignee_user_id=op.id, assignee_label="test-op"),
        GtmInitiative(period="30d", objective_label="not mine", status="suggested",
                      assignee_label="someone-else"),
    ])
    db.commit()
    r = client.get("/admin/gtm-tasks",
                   headers={"Authorization": f"Bearer {operator_token}"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["objective_label"] == "mine"


def test_gtm_tasks_readonly_sees_own_only(client, readonly_token, db):
    client.get("/admin/gtm-tasks", headers={"Authorization": f"Bearer {readonly_token}"})
    ro = db.query(User).filter(User.username == "test-ro").first()
    db.add_all([
        GtmInitiative(period="30d", objective_label="mine ro", status="applied",
                      assignee_user_id=ro.id, assignee_label="test-ro"),
        GtmInitiative(period="60d", objective_label="theirs", status="suggested"),
    ])
    db.commit()
    r = client.get("/admin/gtm-tasks",
                   headers={"Authorization": f"Bearer {readonly_token}"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["objective_label"] == "mine ro"


# ---------------------------------------------------------------------------
# Task 14: GET /gtm-tasks/calendar + POST /gtm-tasks/{id}/assign
# ---------------------------------------------------------------------------

def test_gtm_tasks_calendar_returns_window(client, operator_token, db):
    client.get("/admin/gtm-tasks", headers={"Authorization": f"Bearer {operator_token}"})
    op = db.query(User).filter(User.username == "test-op").first()
    now = datetime.now(timezone.utc)
    db.add_all([
        GtmInitiative(period="30d", objective_label="in window", status="suggested",
                      due_at=now + timedelta(days=10), assignee_user_id=op.id),
        GtmInitiative(period="60d", objective_label="out of window", status="suggested",
                      due_at=now + timedelta(days=100), assignee_user_id=op.id),
    ])
    db.commit()
    r = client.get(
        f"/admin/gtm-tasks/calendar?from={(now - timedelta(days=1)).isoformat()}&to={(now + timedelta(days=30)).isoformat()}",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["label"].startswith("in window")


def test_assign_admin_only(client, admin_token, operator_token, db):
    client.get("/admin/gtm-tasks", headers={"Authorization": f"Bearer {operator_token}"})
    op = db.query(User).filter(User.username == "test-op").first()
    init = GtmInitiative(period="30d", objective_label="x", status="suggested")
    db.add(init); db.commit(); db.refresh(init)

    r_op = client.post(f"/admin/gtm-tasks/{init.id}/assign",
                       json={"user_id": str(op.id)},
                       headers={"Authorization": f"Bearer {operator_token}"})
    assert r_op.status_code == 403

    r_ad = client.post(f"/admin/gtm-tasks/{init.id}/assign",
                       json={"user_id": str(op.id)},
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert r_ad.status_code == 200
    db.refresh(init)
    assert init.assignee_user_id == op.id


# ---------------------------------------------------------------------------
# Task 15: Webhook → GTM extractor background task
# ---------------------------------------------------------------------------

def test_webhook_routes_to_generator(client, db, monkeypatch):
    _seed_corpus(db)
    _mock_anthropic(monkeypatch)

    # Seed the system row the webhook handler resolves by slug.
    from app.models.system import System
    system = System(
        slug="esteps-leads",
        name="eSteps Leads",
        webhook_secret="test-secret",
        is_active=True,
    )
    db.add(system)
    db.commit()

    # Bypass HMAC validation — test env is "test", not "development", so the
    # guard is active. Patch the async helper so it becomes a no-op.
    import app.routers.webhooks as _wh

    async def _noop_verify(*args, **kwargs):
        return None

    monkeypatch.setattr(_wh, "_require_valid_signature", _noop_verify)

    r = client.post("/webhooks/esteps-leads", json={
        "workflow_id": "est-gtm-ingest",
        "execution_id": "exec-test-gtm-1",
        "status": "success",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
    assert r.status_code == 200

    latest = db.query(AIRequest).filter(AIRequest.request_type == "gtm_retrospective").first()
    assert latest is not None
    assert latest.input_preview == "webhook:est-gtm-ingest"
