"""Unit tests for llm.openai_compat._extract_safe and helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ht_lens.llm.errors import EmptyLLMResponseError, LLMTransientError
from ht_lens.llm.openai_compat import _content_str, _extract_safe


def _make_response(content: object, finish_reason: str = "stop", model: str = "test") -> object:
    """Build a minimal mock chat completion response."""
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.model = model
    return response


# ---------------------------------------------------------------------------
# finish_reason='length'
# ---------------------------------------------------------------------------


def test_extract_safe_raises_transient_on_length_with_empty_content() -> None:
    resp = _make_response(content="", finish_reason="length")
    with pytest.raises(LLMTransientError):
        _extract_safe(resp)


def test_extract_safe_raises_transient_on_length_with_nonempty_content() -> None:
    """Truncated but non-empty content is still transient — retry is safer than partial text."""
    resp = _make_response(content="partial trans", finish_reason="length")
    with pytest.raises(LLMTransientError):
        _extract_safe(resp)


# ---------------------------------------------------------------------------
# Empty / None content
# ---------------------------------------------------------------------------


def test_extract_safe_raises_empty_on_none_content() -> None:
    resp = _make_response(content=None)
    with pytest.raises(EmptyLLMResponseError):
        _extract_safe(resp)


def test_extract_safe_raises_empty_on_whitespace_content() -> None:
    resp = _make_response(content="   ")
    with pytest.raises(EmptyLLMResponseError):
        _extract_safe(resp)


def test_extract_safe_raises_empty_on_empty_string() -> None:
    resp = _make_response(content="")
    with pytest.raises(EmptyLLMResponseError):
        _extract_safe(resp)


# ---------------------------------------------------------------------------
# Normal content
# ---------------------------------------------------------------------------


def test_extract_safe_returns_stripped_string() -> None:
    resp = _make_response(content="  hello  ")
    assert _extract_safe(resp) == "hello"


def test_extract_safe_passes_stop_finish_reason() -> None:
    resp = _make_response(content="translation", finish_reason="stop")
    assert _extract_safe(resp) == "translation"


# ---------------------------------------------------------------------------
# _content_str: list / None handling
# ---------------------------------------------------------------------------


def test_content_str_handles_none() -> None:
    assert _content_str(None) == ""


def test_content_str_handles_plain_string() -> None:
    assert _content_str("hello") == "hello"


def test_content_str_handles_list_of_dicts() -> None:
    parts = [{"type": "text", "text": "foo"}, {"type": "text", "text": "bar"}]
    assert _content_str(parts) == "foobar"


def test_content_str_handles_list_of_objects_with_text_attr() -> None:
    item = MagicMock()
    item.text = "baz"
    assert _content_str([item]) == "baz"


def test_extract_safe_handles_list_content() -> None:
    parts = [{"type": "text", "text": "translated"}]
    resp = _make_response(content=parts)
    assert _extract_safe(resp) == "translated"
