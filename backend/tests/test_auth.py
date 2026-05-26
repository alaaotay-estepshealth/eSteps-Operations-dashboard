from app.auth import hash_password
from app.models import User


def test_login_success(client, db_session):
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
    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload
    assert payload["role"] == "admin"


def test_login_failure(client):
    response = client.post(
        "/auth/token",
        data={"username": "missing", "password": "bad"},
    )
    assert response.status_code == 401
