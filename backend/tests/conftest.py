import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AUTO_CREATE_DB", "false")

if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL")

# Safety guard: this suite drops_all/create_all on DATABASE_URL. Refuse to run
# against a production Supabase DB — set TEST_DATABASE_URL to a throwaway Postgres.
_active_db = os.environ.get("DATABASE_URL", "")
if not _active_db:
    raise RuntimeError(
        "Tests need a database. Set TEST_DATABASE_URL to a throwaway Postgres "
        "(e.g. a local docker postgres) — never your production Supabase URL."
    )
if "supabase" in _active_db and not os.getenv("TEST_DATABASE_URL"):
    raise RuntimeError(
        "Refusing to run tests: DATABASE_URL points at Supabase and would be wiped by "
        "drop_all/create_all. Set TEST_DATABASE_URL to a throwaway Postgres first."
    )

from app.main import app
from app.database import Base, get_db
from app.models import (
    Booking,
    Ticket,
    WorkflowExecution,
    AIRequest,
    AuditLog,
    User,
)
from app.models.gtm_initiative import GtmInitiative
from app.models.strategy_asset import StrategyAsset
from app.models.system import System

engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_db(db_session):
    # Order matters: child rows / FK referrers first, systems last (audit_logs,
    # ai_requests, workflow_executions all carry a system_id FK).
    for model in [
        GtmInitiative,
        AuditLog,
        AIRequest,
        WorkflowExecution,
        Ticket,
        Booking,
        User,
        StrategyAsset,
        System,
    ]:
        db_session.query(model).delete()
    db_session.commit()
    yield


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


# ── ES-OPS-09-MEET-NOTES additions (Task 5) ───────────────────────────────────
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.database import get_leads_db


@pytest.fixture()
def db(db_session):
    """Alias of `db_session` so tests can use a shorter name."""
    return db_session


@pytest.fixture()
def admin_token(db_session):
    """Create an admin User row + JWT. get_current_user looks the user up by sub."""
    existing = db_session.query(User).filter(User.username == "test-admin").first()
    if not existing:
        db_session.add(
            User(
                username="test-admin",
                email="test-admin@example.com",
                hashed_password="x",
                role="admin",
                is_active=True,
            )
        )
        db_session.commit()
    return create_access_token({"sub": "test-admin", "role": "admin"})


@pytest.fixture()
def operator_token(db_session):
    existing = db_session.query(User).filter(User.username == "test-op").first()
    if not existing:
        db_session.add(
            User(
                username="test-op",
                email="test-op@example.com",
                hashed_password="x",
                role="operator",
                is_active=True,
            )
        )
        db_session.commit()
    return create_access_token({"sub": "test-op", "role": "operator"})


@pytest.fixture()
def readonly_token(db_session):
    existing = db_session.query(User).filter(User.username == "test-ro").first()
    if not existing:
        db_session.add(
            User(
                username="test-ro",
                email="test-ro@example.com",
                hashed_password="x",
                role="readonly",
                is_active=True,
            )
        )
        db_session.commit()
    return create_access_token({"sub": "test-ro", "role": "readonly"})


@pytest.fixture()
def leads_db():
    gen = get_leads_db()
    db: Session = next(gen)
    try:
        yield db
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
