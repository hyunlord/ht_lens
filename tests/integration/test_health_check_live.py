"""Live health-check test — requires a running sglang endpoint.

Skip automatically when LLM_BASE_URL is not set.
"""

from __future__ import annotations

import os

import pytest

from ht_lens.llm.openai_compat import OpenAICompatibleClient


@pytest.mark.llm
@pytest.mark.asyncio
async def test_health_check_returns_true() -> None:
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not model:
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set")
    client = OpenAICompatibleClient(base_url=base_url, model=model)
    result = await client.health_check()
    assert result is True


@pytest.mark.llm
@pytest.mark.asyncio
async def test_health_check_reasoning_tokens_zero() -> None:
    """Verifies enable_thinking=False is effective (no reasoning tokens leaked)."""
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not model:
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set")
    # health_check() already asserts reasoning_tokens == 0 internally
    client = OpenAICompatibleClient(base_url=base_url, model=model, enable_thinking=False)
    assert await client.health_check() is True
