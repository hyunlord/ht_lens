"""Provider-agnostic LLM client interfaces.

Phase 2a defined a single ``LLMClient`` Protocol carrying both ``translate``
and ``chat``. Phase 6e (LLM Routing Split) separates the two so callers can
route translate traffic and chat traffic to different backends — or to the
same backend with different ``max_tokens`` / ``temperature`` settings.

Structural typing: a single concrete client that implements both methods
(the normal case: same sglang serving everything) continues to satisfy both
``TranslateLLMClient`` and ``ChatLLMClient``. Existing implementations
(``OpenAICompatibleClient``, ``MockLLMClient``) need no shape change.

``LLMClient`` remains as a legacy alias pointing at ``TranslateLLMClient``
so pre-Phase-6e imports keep working. No deprecation warning emitted in
this phase (challenge §1-b — defer to when a second client actually lands).
"""

from __future__ import annotations

from typing import Literal, Protocol, TypedDict, runtime_checkable

Role = Literal["system", "user", "assistant"]


class Message(TypedDict):
    role: Role
    content: str


@runtime_checkable
class TranslateLLMClient(Protocol):
    """LLM used to translate a single block of source text.

    Tuned for short, deterministic output. ``temperature=0.0`` and
    ``max_tokens=2048`` are passed by ``from_env_translate``.
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

    async def health_check(self) -> bool:
        """Returns ``True`` if the underlying provider is reachable."""
        ...


@runtime_checkable
class ChatLLMClient(Protocol):
    """LLM used for Q&A / explain / summarize.

    Tuned for longer answers (``max_tokens=4096``) and slightly higher
    temperature (``0.2``). Applied by ``from_env_chat``.
    """

    async def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
    ) -> str:
        """Multi-turn chat. Returns the assistant message content."""
        ...

    async def health_check(self) -> bool:
        """Returns ``True`` if the underlying provider is reachable."""
        ...


# Legacy alias for pre-Phase-6e imports. Resolves to the translate protocol;
# implementations that satisfy both protocols (the common case) continue to
# work everywhere.
LLMClient = TranslateLLMClient


__all__ = [
    "ChatLLMClient",
    "LLMClient",
    "Message",
    "Role",
    "TranslateLLMClient",
]
