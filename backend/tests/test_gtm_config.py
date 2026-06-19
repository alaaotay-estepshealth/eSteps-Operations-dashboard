def test_gtm_settings_load():
    from app.config import settings
    assert hasattr(settings, "anthropic_api_key")
    assert settings.gtm_model == "claude-opus-4-7"
    assert isinstance(settings.gtm_ai_budget_usd, float)
    assert settings.anthropic_api_url.startswith("https://")
