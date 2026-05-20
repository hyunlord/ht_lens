"""LLMClient factory keyed by ``LLM_PROVIDER`` env var.

Phase 2a only knows about ``"mock"``. ``"openai_compat"`` (sglang/Ollama/
OpenRouter) lands in Phase 2b; until then it raises ``NotImplementedError`` so
calls fail loudly rather than silently using a different provider.
"""

from __future__ import annotations

import os

from ht_lens.llm.client import LLMClient
from ht_lens.llm.mock import MockLLMClient


def from_env() -> LLMClient:
    """Build an :class:`LLMClient` based on the ``LLM_PROVIDER`` env var.

    Currently supports ``"mock"`` (default). Any other value raises
    ``NotImplementedError``.
    """
    provider = os.environ.get("LLM_PROVIDER", "mock")
    if provider == "mock":
        return MockLLMClient()
    raise NotImplementedError(
        f"LLM provider {provider!r} is not implemented in Phase 2a. "
        "Set LLM_PROVIDER=mock or wait for Phase 2b (openai_compat)."
    )


__all__ = ["from_env"]
