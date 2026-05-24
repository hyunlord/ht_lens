"""LLM domain errors — phase 2b."""

from __future__ import annotations


class LLMError(Exception):
    """Base class for all LLM-related errors."""


class EmptyLLMResponseError(LLMError):
    """LLM returned empty or truncated content.

    Raised when:
    - ``finish_reason == "length"`` (response was cut off)
    - ``message.content`` is ``None``, empty, or whitespace-only
    """


class LLMTransientError(LLMError):
    """Temporary failure that may succeed on retry (5xx, timeout, rate limit)."""


class LLMPermanentError(LLMError):
    """Non-retryable failure (4xx auth/bad-request). Retry will not help."""


class LLMHealthCheckFailed(LLMError):
    """``health_check()`` failed — endpoint unreachable or chat template regressed."""


class LLMConfigurationError(LLMError):
    """LLM provider not explicitly configured — Phase 6e-2.

    Raised by ``from_env_translate()`` / ``from_env_chat()`` when neither
    the scoped ``TRANSLATE_LLM_PROVIDER`` / ``CHAT_LLM_PROVIDER`` nor the
    legacy ``LLM_PROVIDER`` is set (or present but empty). Prevents the
    factory from silently selecting ``MockLLMClient`` when shell exports
    are missing and the repo ``.env`` did not load — the failure mode
    that polluted prod DB with ``[KO] <english>`` mock output. Tests can
    still pin ``LLM_PROVIDER=mock`` to opt into mock explicitly.
    """


__all__ = [
    "EmptyLLMResponseError",
    "LLMConfigurationError",
    "LLMError",
    "LLMHealthCheckFailed",
    "LLMPermanentError",
    "LLMTransientError",
]
