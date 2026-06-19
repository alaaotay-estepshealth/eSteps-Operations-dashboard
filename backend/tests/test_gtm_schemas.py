import pytest
from pydantic import ValidationError

from app.schemas.gtm_plan import GtmAiOutput, KpiTarget, RiskFlag, SourceFile


def test_valid_ai_output_parses():
    payload = {
        "executive_summary": "## Where we stand\n...",
        "kpi_targets": [
            {"period": "30d", "objective": "PT clinic pilots", "target": 2,
             "unit": "pilots", "rationale": "from 02_PRODUCTS.md", "assignee_label": "Nidhal"}
        ],
        "risk_flags": [
            {"label": "No founder content", "severity": "high", "source": "01_STRATEGY.md"}
        ],
        "recommended_focus": ["Hire GCA", "Stand up landing"],
        "source_files": [
            {"name": "01_STRATEGY.md", "path": "GTM-2026-OS/01_STRATEGY.md", "tokens": 25000}
        ],
    }
    out = GtmAiOutput.model_validate(payload)
    assert len(out.kpi_targets) == 1
    assert out.kpi_targets[0].period == "30d"


def test_missing_executive_summary_fails():
    with pytest.raises(ValidationError):
        GtmAiOutput.model_validate({"kpi_targets": [], "risk_flags": [], "recommended_focus": [], "source_files": []})


def test_invalid_period_fails():
    with pytest.raises(ValidationError):
        KpiTarget.model_validate({
            "period": "45d",  # not in {30d,60d,90d}
            "objective": "x",
            "target": 1,
            "unit": "u",
            "rationale": "r",
            "assignee_label": "x",
        })


def test_invalid_severity_fails():
    with pytest.raises(ValidationError):
        RiskFlag.model_validate({"label": "x", "severity": "extreme", "source": "y"})


def test_kpi_target_optional_fields_default():
    k = KpiTarget.model_validate({
        "period": "60d",
        "objective": "Research",
        "rationale": "r",
    })
    assert k.target is None
    assert k.unit is None
    assert k.assignee_label is None
