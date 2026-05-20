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


__all__ = [
    "EmptyLLMResponseError",
    "LLMError",
    "LLMHealthCheckFailed",
    "LLMPermanentError",
    "LLMTransientError",
]
