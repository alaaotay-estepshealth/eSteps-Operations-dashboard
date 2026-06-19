import json
from unittest.mock import MagicMock

import pytest

from app.models.ai_request import AIRequest
from app.models.gtm_initiative import GtmInitiative
from app.models.strategy_asset import StrategyAsset
from app.models.user import User
from app.services.gtm_extractor import (
    generate_gtm_plan,
    load_corpus,
    resolve_assignee,
    upsert_initiatives,
    GtmExtractorError,
)


@pytest.fixture
def seed_corpus(db):
    db.add_all([
        StrategyAsset(
            relative_path="GTM-2026-OS/01_STRATEGY.md",
            parent_path="GTM-2026-OS",
            name="01_STRATEGY.md",
            is_folder=False,
            mime_type="text/markdown",
            size_bytes=10,
            content=b"# strategy text\n\n## ten principles",
        ),
        StrategyAsset(
            relative_path="GTM-2026-OS/02_PRODUCTS.md",
            parent_path="GTM-2026-OS",
            name="02_PRODUCTS.md",
            is_folder=False,
            mime_type="text/markdown",
            size_bytes=10,
            content=b"# products\n\nHealth, Mitus, Studio",
        ),
        # outside scope — should be ignored
        StrategyAsset(
            relative_path="1-playbooks/Other.md",
            parent_path="1-playbooks",
            name="Other.md",
            is_folder=False,
            mime_type="text/markdown",
            size_bytes=10,
            content=b"# other",
        ),
    ])
    db.commit()


def test_load_corpus_filters_to_gtm_os(db, seed_corpus):
    files = load_corpus(db)
    paths = [f["path"] for f in files]
    assert "GTM-2026-OS/01_STRATEGY.md" in paths
    assert "GTM-2026-OS/02_PRODUCTS.md" in paths
    assert "1-playbooks/Other.md" not in paths
    assert all("content" in f for f in files)


def test_resolve_assignee_matches_username(db):
    db.add(User(username="nidhal", email="n@e.com", hashed_password="x", role="operator", is_active=True))
    db.commit()
    user_id = resolve_assignee(db, "Nidhal")
    assert user_id is not None


def test_resolve_assignee_matches_display_name(db):
    db.add(User(username="op1", display_name="Growth Content Associate",
                email="g@e.com", hashed_password="x", role="operator", is_active=True))
    db.commit()
    user_id = resolve_assignee(db, "Growth Content Associate")
    assert user_id is not None


def test_resolve_assignee_no_match_returns_none(db):
    assert resolve_assignee(db, "Nobody") is None


def test_upsert_initiatives_supersedes_prior(db):
    ai_req = AIRequest(request_type="gtm_retrospective", provider="anthropic", model="claude-opus-4-7",
                       status="completed", tokens_used=100, cost_usd=0.01)
    db.add(ai_req); db.commit(); db.refresh(ai_req)

    # First run
    upsert_initiatives(db, source_ai_request_id=ai_req.id, kpi_targets=[
        {"period": "30d", "objective": "old", "target": 1, "unit": "u",
         "rationale": "r", "assignee_label": "Nidhal"},
    ])
    db.commit()
    assert db.query(GtmInitiative).filter_by(status="suggested").count() == 1

    # Second run — same period, new objective
    ai_req2 = AIRequest(request_type="gtm_retrospective", provider="anthropic", model="claude-opus-4-7",
                        status="completed", tokens_used=100, cost_usd=0.01)
    db.add(ai_req2); db.commit(); db.refresh(ai_req2)
    upsert_initiatives(db, source_ai_request_id=ai_req2.id, kpi_targets=[
        {"period": "30d", "objective": "new", "target": 2, "unit": "u",
         "rationale": "r", "assignee_label": "Nidhal"},
    ])
    db.commit()

    superseded = db.query(GtmInitiative).filter_by(status="superseded").all()
    suggested = db.query(GtmInitiative).filter_by(status="suggested").all()
    assert len(superseded) == 1
    assert superseded[0].objective_label == "old"
    assert len(suggested) == 1
    assert suggested[0].objective_label == "new"


def test_upsert_initiatives_preserves_applied(db):
    ai_req = AIRequest(request_type="gtm_retrospective", provider="anthropic", model="claude-opus-4-7",
                      status="completed", tokens_used=100, cost_usd=0.01)
    db.add(ai_req); db.commit(); db.refresh(ai_req)

    # Mark a prior 30d row as applied
    applied = GtmInitiative(period="30d", objective_label="applied target", status="applied",
                            source_ai_request_id=ai_req.id)
    db.add(applied); db.commit()

    ai_req2 = AIRequest(request_type="gtm_retrospective", provider="anthropic", model="claude-opus-4-7",
                       status="completed", tokens_used=100, cost_usd=0.01)
    db.add(ai_req2); db.commit(); db.refresh(ai_req2)
    upsert_initiatives(db, source_ai_request_id=ai_req2.id, kpi_targets=[
        {"period": "30d", "objective": "new", "target": 2, "unit": "u",
         "rationale": "r", "assignee_label": "Nidhal"},
    ])
    db.commit()
    applied_after = db.query(GtmInitiative).filter_by(status="applied").count()
    assert applied_after == 1


def test_generate_gtm_plan_end_to_end(db, seed_corpus, monkeypatch):
    fake_text = json.dumps({
        "executive_summary": "ok",
        "kpi_targets": [
            {"period": "30d", "objective": "PT clinic pilots", "target": 2,
             "unit": "pilots", "rationale": "from 02_PRODUCTS.md", "assignee_label": "Nidhal"}
        ],
        "risk_flags": [],
        "recommended_focus": ["Hire GCA"],
        "source_files": [
            {"name": "01_STRATEGY.md", "path": "GTM-2026-OS/01_STRATEGY.md", "tokens": 100},
        ],
    })
    monkeypatch.setattr(
        "app.services.gtm_extractor.call_anthropic",
        MagicMock(return_value={"text": fake_text, "usage": {"input_tokens": 100, "output_tokens": 50,
                                                              "cache_creation_input_tokens": 0,
                                                              "cache_read_input_tokens": 0}}),
    )

    ai_req = generate_gtm_plan(db)
    assert ai_req.status == "completed"
    assert db.query(GtmInitiative).filter_by(status="suggested").count() == 1
    row = db.query(GtmInitiative).filter_by(status="suggested").first()
    assert row.objective_label == "PT clinic pilots"
    assert row.source_ai_request_id == ai_req.id


def test_generate_gtm_plan_rejects_bad_json(db, seed_corpus, monkeypatch):
    monkeypatch.setattr(
        "app.services.gtm_extractor.call_anthropic",
        MagicMock(return_value={"text": "not json", "usage": {"input_tokens": 1, "output_tokens": 1,
                                                              "cache_creation_input_tokens": 0,
                                                              "cache_read_input_tokens": 0}}),
    )
    ai_req = generate_gtm_plan(db)
    assert ai_req.status == "rejected"
    assert db.query(GtmInitiative).count() == 0


def test_generate_gtm_plan_empty_corpus_raises(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.gtm_extractor.call_anthropic",
        MagicMock(),
    )
    with pytest.raises(GtmExtractorError, match="empty"):
        generate_gtm_plan(db)
