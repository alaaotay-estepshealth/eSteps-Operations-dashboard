"""Direct Anthropic Messages API client for GTM ingest.

Mirrors gemini.py: synchronous httpx, no SDK, ~50 LoC. Supports prompt caching
via cache_control blocks. Used only by gtm_extractor — not for general LLM ops.

Pricing constants are baked in for claude-opus-4-7 as of 2026-Q3. When pricing
changes, bump _OPUS_PRICING_USD_PER_MTOK + add a note with the effective date.
ai_requests.tokens_used is stored so historical cost is always recomputable.
"""
import time
from typing import Any, Dict, List

import httpx

from app.config import settings


class AnthropicError(RuntimeError):
    pass


# 2026-Q3 list price for claude-opus-4-7 (USD per million tokens).
_OPUS_PRICING_USD_PER_MTOK = {
    "input": 15.0,
    "output": 75.0,
    "cache_read": 1.5,
    "cache_creation": 18.75,  # 1.25x input
}

_DEFAULT_TIMEOUT_SECONDS = 90.0
_MAX_RETRIES = 1
_RETRY_BACKOFF_SECONDS = 2.0


def call_anthropic(
    *,
    system_blocks: List[Dict[str, Any]],
    user_message: str,
    model: str | None = None,
    max_tokens: int = 8192,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """POST /v1/messages and return {text, usage}.

    system_blocks: list of content blocks for the system prompt. The last block
    intended for caching should include `cache_control: {"type": "ephemeral"}`.

    Retries once on 5xx/timeouts; fails fast on 4xx.
    """
    if not settings.anthropic_api_key:
        raise AnthropicError("Anthropic API key not configured (set ANTHROPIC_API_KEY).")

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": settings.anthropic_version,
        "content-type": "application/json",
    }
    body = {
        "model": model or settings.gtm_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_blocks,
        "messages": [{"role": "user", "content": user_message}],
    }

    attempt = 0
    while True:
        try:
            with httpx.Client(timeout=_DEFAULT_TIMEOUT_SECONDS) as c:
                resp = c.post(settings.anthropic_api_url, headers=headers, json=body)
            if resp.status_code == 200:
                data = resp.json()
                text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
                return {
                    "text": "".join(text_blocks),
                    "usage": data.get("usage", {}),
                    "stop_reason": data.get("stop_reason"),
                    "raw_id": data.get("id"),
                }
            if 400 <= resp.status_code < 500:
                raise AnthropicError(f"Anthropic {resp.status_code}: {resp.text[:500]}")
            if attempt >= _MAX_RETRIES:
                raise AnthropicError(f"Anthropic {resp.status_code} after retries: {resp.text[:500]}")
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt >= _MAX_RETRIES:
                raise AnthropicError(f"Anthropic network error: {e}") from e
        attempt += 1
        time.sleep(_RETRY_BACKOFF_SECONDS)


def compute_cost(usage: Dict[str, int]) -> float:
    """Return USD cost for a single Anthropic call given the usage dict."""
    p = _OPUS_PRICING_USD_PER_MTOK
    return (
        usage.get("input_tokens", 0) / 1e6 * p["input"]
        + usage.get("output_tokens", 0) / 1e6 * p["output"]
        + usage.get("cache_read_input_tokens", 0) / 1e6 * p["cache_read"]
        + usage.get("cache_creation_input_tokens", 0) / 1e6 * p["cache_creation"]
    )
