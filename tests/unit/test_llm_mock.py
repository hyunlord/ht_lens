"""Unit tests for MockLLMClient and LLMClient protocol conformance."""

from __future__ import annotations

import pytest

from ht_lens.llm.client import LLMClient, Message
from ht_lens.llm.factory import from_env
from ht_lens.llm.mock import MockLLMClient


@pytest.mark.asyncio
async def test_mock_translate_wraps_text_with_target_lang() -> None:
    client = MockLLMClient()
    result = await client.translate("Hello world", src="en", tgt="ko")
    assert result == "[KO] Hello world"


@pytest.mark.asyncio
async def test_mock_translate_uppercases_tgt() -> None:
    client = MockLLMClient()
    result = await client.translate("hi", src="ko", tgt="en")
    assert result.startswith("[EN]")


@pytest.mark.asyncio
async def test_mock_chat_echoes_last_user_message() -> None:
    client = MockLLMClient()
    messages: list[Message] = [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "Are you sure?"},
    ]
    result = await client.chat(messages)
    assert result == "mock: Are you sure?"


@pytest.mark.asyncio
async def test_mock_chat_single_message() -> None:
    client = MockLLMClient()
    messages: list[Message] = [{"role": "user", "content": "Hello"}]
    assert await client.chat(messages) == "mock: Hello"


@pytest.mark.asyncio
async def test_mock_health_check_returns_true() -> None:
    client = MockLLMClient()
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_mock_client_satisfies_protocol() -> None:
    client: LLMClient = MockLLMClient()
    assert await client.health_check() is True


def test_from_env_returns_mock_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    client = from_env()
    assert isinstance(client, MockLLMClient)


def test_from_env_returns_mock_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    client = from_env()
    assert isinstance(client, MockLLMClient)


def test_from_env_raises_for_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "nonexistent_provider")
    with pytest.raises(NotImplementedError, match="nonexistent_provider"):
        from_env()


def test_from_env_returns_openai_compat_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from ht_lens.llm.openai_compat import OpenAICompatibleClient

    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    client = from_env()
    assert isinstance(client, OpenAICompatibleClient)
