from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.anthropic import call_anthropic, compute_cost, AnthropicError


def _mock_response(usage=None, text='{"executive_summary":"ok","kpi_targets":[],"risk_flags":[],"recommended_focus":[],"source_files":[]}'):
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={
            "id": "msg_test",
            "content": [{"type": "text", "text": text}],
            "usage": usage or {"input_tokens": 100, "output_tokens": 200,
                               "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "stop_reason": "end_turn",
        }),
    )


def test_call_anthropic_happy_path(monkeypatch):
    fake_post = MagicMock(return_value=_mock_response())
    monkeypatch.setattr("httpx.Client.post", fake_post)
    monkeypatch.setattr("app.services.anthropic.settings.anthropic_api_key", "test-key")

    result = call_anthropic(
        system_blocks=[{"type": "text", "text": "you are a strategist", "cache_control": {"type": "ephemeral"}}],
        user_message="generate",
    )
    assert result["text"].startswith("{")
    assert result["usage"]["input_tokens"] == 100
    fake_post.assert_called_once()
    call_args = fake_post.call_args
    assert call_args.kwargs["headers"]["x-api-key"] == "test-key"
    assert "anthropic-version" in call_args.kwargs["headers"]


def test_call_anthropic_missing_key_raises(monkeypatch):
    monkeypatch.setattr("app.services.anthropic.settings.anthropic_api_key", "")
    with pytest.raises(AnthropicError, match="not configured"):
        call_anthropic(system_blocks=[], user_message="x")


def test_call_anthropic_5xx_retries(monkeypatch):
    calls = []
    def fake_post(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            return MagicMock(status_code=500, text="server error")
        return _mock_response()
    monkeypatch.setattr("httpx.Client.post", fake_post)
    monkeypatch.setattr("app.services.anthropic.settings.anthropic_api_key", "test-key")
    monkeypatch.setattr("app.services.anthropic.time.sleep", lambda _: None)

    result = call_anthropic(system_blocks=[], user_message="x")
    assert len(calls) == 2
    assert result["usage"]["input_tokens"] == 100


def test_call_anthropic_4xx_no_retry(monkeypatch):
    calls = []
    def fake_post(*a, **kw):
        calls.append(1)
        return MagicMock(status_code=400, text="bad")
    monkeypatch.setattr("httpx.Client.post", fake_post)
    monkeypatch.setattr("app.services.anthropic.settings.anthropic_api_key", "test-key")

    with pytest.raises(AnthropicError):
        call_anthropic(system_blocks=[], user_message="x")
    assert len(calls) == 1


def test_compute_cost_uncached():
    usage = {"input_tokens": 80_000, "output_tokens": 8_000,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    cost = compute_cost(usage)
    # $15/MTok input + $75/MTok output
    assert cost == pytest.approx(80_000 / 1e6 * 15.0 + 8_000 / 1e6 * 75.0, rel=1e-3)


def test_compute_cost_cached():
    usage = {"input_tokens": 0, "output_tokens": 8_000,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 80_000}
    cost = compute_cost(usage)
    # $1.50/MTok cache_read + $75/MTok output
    assert cost == pytest.approx(80_000 / 1e6 * 1.5 + 8_000 / 1e6 * 75.0, rel=1e-3)
