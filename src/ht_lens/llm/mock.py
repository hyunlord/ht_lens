"""Deterministic mock LLM client.

Used by tests and any code path that needs an :class:`LLMClient` without
touching a real provider. Output shape is stable so tests can assert on it.
"""

from __future__ import annotations

from ht_lens.llm.client import Message


class MockLLMClient:
    """Deterministic, zero-cost LLM client.

    - :meth:`translate` returns ``"[<TGT>] <text>"`` for traceable assertions.
    - :meth:`chat` echoes the last user message, or ``"mock response"`` if none.
    - :meth:`health_check` always succeeds.
    """

    model_name: str = "mock"

    async def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        *,
        context: str | None = None,
    ) -> str:
        del src, context  # unused — deterministic mock
        return f"[{tgt.upper()}] {text}"

    async def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
    ) -> str:
        del system  # not used by the mock
        for msg in reversed(messages):
            if msg["role"] == "user":
                return f"mock: {msg['content']}"
        return "mock response"

    async def health_check(self) -> bool:
        return True


class FailMockLLMClient(MockLLMClient):
    """MockLLMClient variant that always raises LLMPermanentError on translate.

    Used by subprocess-level tests to trigger stats.failed > 0 via LLM_PROVIDER=mock_fail.
    """

    async def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        *,
        context: str | None = None,
    ) -> str:
        from ht_lens.llm.errors import LLMPermanentError

        raise LLMPermanentError("mock permanent failure")


__all__ = ["FailMockLLMClient", "MockLLMClient"]
