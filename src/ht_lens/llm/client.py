"""Provider-agnostic LLM client interface.

The signature is fixed in Phase 2a (per phase prompt) so Phase 2b can implement
``OpenAICompatibleClient`` without re-shaping callers.
"""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict

Role = Literal["system", "user", "assistant"]


class Message(TypedDict):
    role: Role
    content: str


class LLMClient(Protocol):
    """Provider-agnostic LLM client.

    Phase 2a defines the interface; real implementations live in Phase 2b.
    """

    async def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        *,
        context: str | None = None,
    ) -> str:
        """Translate ``text`` from ``src`` to ``tgt``. Returns translation only,
        no preamble or quoting."""
        ...

    async def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
    ) -> str:
        """Multi-turn chat. Returns the assistant message content."""
        ...

    async def health_check(self) -> bool:
        """Returns ``True`` if the underlying provider is reachable. Implementations
        should be cheap (no real generation)."""
        ...
