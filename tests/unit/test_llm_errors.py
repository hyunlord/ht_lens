"""Unit tests for LLM error hierarchy."""

from __future__ import annotations

import pytest

from ht_lens.llm.errors import (
    EmptyLLMResponseError,
    LLMError,
    LLMHealthCheckFailed,
    LLMPermanentError,
    LLMTransientError,
)


def test_all_errors_are_llm_error_subclasses() -> None:
    for cls in (
        EmptyLLMResponseError,
        LLMTransientError,
        LLMPermanentError,
        LLMHealthCheckFailed,
    ):
        assert issubclass(cls, LLMError)


def test_llm_error_is_exception() -> None:
    assert issubclass(LLMError, Exception)


def test_errors_are_distinguishable() -> None:
    assert not issubclass(LLMTransientError, LLMPermanentError)
    assert not issubclass(LLMPermanentError, LLMTransientError)
    assert not issubclass(EmptyLLMResponseError, LLMTransientError)


def test_error_messages_preserved() -> None:
    exc = LLMTransientError("timeout after 30s")
    assert "timeout" in str(exc)


def test_health_check_failed_is_llm_error() -> None:
    exc = LLMHealthCheckFailed("endpoint unreachable")
    assert isinstance(exc, LLMError)


def test_catch_base_catches_all() -> None:
    for cls in (
        EmptyLLMResponseError,
        LLMTransientError,
        LLMPermanentError,
        LLMHealthCheckFailed,
    ):
        with pytest.raises(LLMError):
            raise cls("test")
