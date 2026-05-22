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

    Used by subprocess-level tests to trigger stats.failed > 0 via
    ``LLM_PROVIDER=mock_fail`` (or ``TRANSLATE_LLM_PROVIDER=mock_fail``).

    Note: asymmetric by design — ``chat()`` is inherited unchanged from
    :class:`MockLLMClient`, so ``CHAT_LLM_PROVIDER=mock_fail`` does NOT
    inject chat-side failures. For chat-side failure injection, patch
    the ``ChatLLMClient`` dependency directly at the test level (e.g.
    ``make_test_client(chat_llm_override=...)``).
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
