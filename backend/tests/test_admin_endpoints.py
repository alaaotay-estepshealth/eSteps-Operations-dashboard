from datetime import datetime, timedelta

from app.auth import hash_password
from app.models import Lead, WorkflowExecution, AIRequest, AuditLog, User


def _auth_headers(client, db_session):
    user = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("admin123"),
        role="admin",
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/auth/token",
        data={"username": "admin", "password": "admin123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_minimal_data(db_session):
    lead = Lead(
        lead_id="EST-00001",
        first_name="Test",
        last_name="Lead",
        email="lead@example.com",
        research_interest="gait_analysis",
        campaign_tag="Priority_A",
        stage="meeting_booked",
        touch_number=2,
        reply_received=True,
        meeting_booked_at=datetime.utcnow(),
        processed_at=datetime.utcnow(),
        process_duration_min=3.5,
        ai_classified=True,
        human_verified=True,
        human_override=False,
    )
    db_session.add(lead)

    ai_request = AIRequest(
        request_type="lead_classify",
        workflow_source="est-2",
        provider="openai",
        model="gpt-4o",
        tokens_used=200,
        cost_usd=0.01,
        confidence_score=0.92,
        used_fallback=False,
        human_verified=True,
        human_override=False,
        status="completed",
    )
    db_session.add(ai_request)

    workflow = WorkflowExecution(
        workflow_id="wf_test",
        workflow_name="WF Test",
        execution_id="exec_test_1",
        status="success",
        started_at=datetime.utcnow() - timedelta(seconds=3),
        finished_at=datetime.utcnow(),
        duration_seconds=3.0,
        retry_count=0,
    )
    db_session.add(workflow)

    log = AuditLog(
        level="ERROR",
        source="fastapi",
        message="Test error",
    )
    db_session.add(log)

    db_session.commit()


def test_dashboard_metrics_requires_auth(client):
    response = client.get("/admin/dashboard/metrics")
    assert response.status_code == 401


def test_dashboard_metrics_ok(client, db_session):
    headers = _auth_headers(client, db_session)
    _seed_minimal_data(db_session)

    response = client.get("/admin/dashboard/metrics", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "hours_saved_week" in payload
    assert payload["total_leads"] >= 1


def test_workflows_status(client, db_session):
    headers = _auth_headers(client, db_session)
    _seed_minimal_data(db_session)

    response = client.get("/admin/workflows/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_ai_decisions(client, db_session):
    headers = _auth_headers(client, db_session)
    _seed_minimal_data(db_session)

    response = client.get("/admin/ai/decisions", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "decisions" in payload


def test_logs_operations(client, db_session):
    headers = _auth_headers(client, db_session)
    _seed_minimal_data(db_session)

    response = client.get("/admin/logs/operations", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "logs" in payload
