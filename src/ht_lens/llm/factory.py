"""LLMClient factory keyed by ``LLM_PROVIDER`` env var.

Phase 2b adds ``"openai_compat"`` (sglang/Ollama/OpenRouter).
"""

from __future__ import annotations

import os

from ht_lens.llm.client import LLMClient


def from_env() -> LLMClient:
    """Build an :class:`LLMClient` based on the ``LLM_PROVIDER`` env var.

    Supported providers:
    - ``"mock"`` (default) — deterministic, no network calls
    - ``"openai_compat"`` — sglang/Ollama/OpenRouter via AsyncOpenAI SDK;
      requires ``LLM_BASE_URL`` and ``LLM_MODEL`` env vars.
    """
    provider = os.environ.get("LLM_PROVIDER", "mock")
    if provider == "mock":
        from ht_lens.llm.mock import MockLLMClient

        return MockLLMClient()
    if provider == "openai_compat":
        from ht_lens.llm.openai_compat import OpenAICompatibleClient

        base_url = os.environ["LLM_BASE_URL"]
        model = os.environ["LLM_MODEL"]
        api_key = os.environ.get("LLM_API_KEY", "EMPTY")
        return OpenAICompatibleClient(base_url=base_url, model=model, api_key=api_key)
    raise NotImplementedError(
        f"LLM provider {provider!r} is not implemented. "
        "Set LLM_PROVIDER=mock or LLM_PROVIDER=openai_compat."
    )


__all__ = ["from_env"]
