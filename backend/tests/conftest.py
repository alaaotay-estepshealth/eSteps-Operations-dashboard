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
    Lead,
    EmailLog,
    Opportunity,
    Booking,
    Ticket,
    WorkflowExecution,
    AIRequest,
    AuditLog,
    User,
)

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
    for model in [
        AuditLog,
        AIRequest,
        WorkflowExecution,
        Ticket,
        Opportunity,
        Booking,
        EmailLog,
        Lead,
        User,
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
