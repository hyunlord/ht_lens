"""Phase 6e — scoped LLM factory tests.

Covers:
- ``TRANSLATE_LLM_*`` / ``CHAT_LLM_*`` scoped env vars are read by
  ``from_env_translate`` / ``from_env_chat``.
- Legacy ``LLM_*`` is honored as a fallback when the scoped key is unset
  or empty.
- Scoped values take precedence over legacy.
- Default ``max_tokens`` is 2048 (translate) / 4096 (chat).
- Empty/whitespace scoped strings fall through to legacy (challenge §2-c).
- Legacy ``from_env()`` returns a translate-equivalent client without
  emitting a ``DeprecationWarning`` in this phase (challenge §1-b).
"""

from __future__ import annotations

import warnings

import pytest

from ht_lens.llm.factory import from_env, from_env_chat, from_env_translate


def test_from_env_translate_uses_scoped_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRANSLATE_LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("TRANSLATE_LLM_BASE_URL", "http://translate.test:8081/v1")
    monkeypatch.setenv("TRANSLATE_LLM_MODEL", "translate-model")
    monkeypatch.setenv("TRANSLATE_LLM_MAX_TOKENS", "1024")
    monkeypatch.setenv("TRANSLATE_LLM_TEMPERATURE", "0.0")
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")
    client = from_env_translate()
    assert client.model_name == "translate-model"
    assert client.max_tokens == 1024
    assert client.temperature == 0.0


def test_from_env_chat_uses_scoped_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("CHAT_LLM_BASE_URL", "http://chat.test:8082/v1")
    monkeypatch.setenv("CHAT_LLM_MODEL", "chat-model")
    monkeypatch.setenv("CHAT_LLM_MAX_TOKENS", "8192")
    monkeypatch.setenv("CHAT_LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")
    client = from_env_chat()
    assert client.model_name == "chat-model"
    assert client.max_tokens == 8192
    assert client.temperature == 0.5


def test_legacy_llm_vars_still_work_for_both_factories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting only ``LLM_*`` (no scoped keys) feeds both factories."""
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "http://legacy.test:8081/v1")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    t = from_env_translate()
    c = from_env_chat()
    assert t.model_name == "legacy-model"
    assert c.model_name == "legacy-model"
    # Defaults still apply when the scoped MAX_TOKENS / TEMPERATURE are unset.
    assert t.max_tokens == 2048
    assert c.max_tokens == 4096
    assert t.temperature == 0.0
    assert c.temperature == 0.2


def test_translate_scoped_overrides_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "http://legacy.test:8081/v1")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    monkeypatch.setenv("TRANSLATE_LLM_BASE_URL", "http://new.test:8082/v1")
    monkeypatch.setenv("TRANSLATE_LLM_MODEL", "new-model")
    t = from_env_translate()
    assert t.model_name == "new-model"
    # Chat still uses legacy because no CHAT_LLM_MODEL was set.
    c = from_env_chat()
    assert c.model_name == "legacy-model"


def test_max_tokens_defaults() -> None:
    """No env vars set → mock provider, defaults 2048/4096 applied."""
    # MockLLMClient has no max_tokens attr, but the factories pick the
    # right openai_compat defaults — we verify against a config that uses
    # openai_compat with a working base_url/model from env. Without those,
    # mock fires which doesn't expose max_tokens. Verify defaults via the
    # constants exported from the module.
    from ht_lens.llm.factory import (
        _CHAT_DEFAULT_MAX_TOKENS,
        _TRANSLATE_DEFAULT_MAX_TOKENS,
    )

    assert _TRANSLATE_DEFAULT_MAX_TOKENS == 2048
    assert _CHAT_DEFAULT_MAX_TOKENS == 4096


def test_scoped_empty_string_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Challenge §2-c — empty scoped string must NOT override a working
    legacy value."""
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "http://legacy.test:8081/v1")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    monkeypatch.setenv("TRANSLATE_LLM_MODEL", "")  # empty — should be ignored
    monkeypatch.setenv("TRANSLATE_LLM_BASE_URL", "   ")  # whitespace — ignored
    client = from_env_translate()
    assert client.model_name == "legacy-model"


def test_from_env_does_not_emit_deprecation_warning() -> None:
    """Challenge §1-b — legacy ``from_env()`` is preserved as a thin
    delegation; no ``DeprecationWarning`` in this phase. Add the warning
    when a second concrete client lands."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from_env()
    assert all(not issubclass(w.category, DeprecationWarning) for w in caught), (
        f"unexpected DeprecationWarning: {[w.message for w in caught]}"
    )
