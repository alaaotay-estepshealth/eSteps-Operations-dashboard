import pytest
from app.models.user import User


def test_user_has_display_name_column(db):
    u = User(
        username="alice",
        email="alice@example.com",
        hashed_password="x",
        role="readonly",
        is_active=True,
        display_name="Alice Cooper",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.display_name == "Alice Cooper"


def test_user_display_name_nullable(db):
    u = User(
        username="bob",
        email="bob@example.com",
        hashed_password="x",
        role="readonly",
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.display_name is None


from app.models.gtm_initiative import GtmInitiative


def test_create_gtm_initiative(db):
    init = GtmInitiative(
        period="30d",
        objective_label="PT clinic pilots",
        target_value=2,
        target_unit="pilots",
        rationale="GTM-2026-OS commits to 2",
        assignee_label="Nidhal",
        status="suggested",
    )
    db.add(init)
    db.commit()
    db.refresh(init)
    assert init.id is not None
    assert init.status == "suggested"
    assert init.created_at is not None


def test_gtm_initiative_default_status(db):
    init = GtmInitiative(period="60d", objective_label="X")
    db.add(init)
    db.commit()
    db.refresh(init)
    assert init.status == "suggested"
