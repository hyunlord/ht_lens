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


def test_from_env_does_not_emit_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Challenge §1-b — legacy ``from_env()`` is preserved as a thin
    delegation; no ``DeprecationWarning`` in this phase. Add the warning
    when a second concrete client lands.

    Phase 6e-2: pin explicit ``LLM_PROVIDER=mock`` so the underlying
    ``from_env_translate()`` does not fail-closed for missing provider.
    The test's intent (warning behavior) is unchanged.
    """
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from_env()
    assert all(not issubclass(w.category, DeprecationWarning) for w in caught), (
        f"unexpected DeprecationWarning: {[w.message for w in caught]}"
    )


def test_concrete_clients_satisfy_both_protocols() -> None:
    """Phase 6e R1 cross-verify §3-claim fix: explicitly verify that the
    concrete clients (MockLLMClient, OpenAICompatibleClient) satisfy
    *both* TranslateLLMClient and ChatLLMClient via runtime_checkable
    structural typing — the whole point of the alias-only legacy approach
    is that this works."""
    from ht_lens.llm.client import ChatLLMClient, TranslateLLMClient
    from ht_lens.llm.mock import MockLLMClient

    mc = MockLLMClient()
    assert isinstance(mc, TranslateLLMClient)
    assert isinstance(mc, ChatLLMClient)


# --- R2 Planner-directed micro-fix #1: chat-side numeric invalid lock ---
#
# R1 RE-CODE locked the translate-timeout invalid → legacy → default path
# but R2 noted the same _resolve_int/_resolve_float code path also serves
# CHAT_LLM_TIMEOUT / CHAT_LLM_MAX_TOKENS / CHAT_LLM_TEMPERATURE — and the
# chat-side cases had no explicit tests. The four cases below mirror the
# translate-side pattern so a future refactor that breaks chat-side
# fallback (or accidentally re-asymmetrises the helpers) is caught.


def _underlying_timeout(client) -> float:
    """Pull the timeout out of the openai SDK client (works for float
    and httpx.Timeout wrappers — same helper shape as
    test_llm_factory_timeout._underlying_timeout_seconds)."""
    underlying = getattr(client, "_client", None)
    raw = underlying.timeout
    if isinstance(raw, int | float):
        return float(raw)
    return float(raw.read or raw.connect or raw.write or raw.pool or 0)


def _build_openai_chat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("CHAT_LLM_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("CHAT_LLM_MODEL", "test-chat-model")
    monkeypatch.setenv("CHAT_LLM_API_KEY", "EMPTY")


def test_chat_timeout_invalid_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHAT_LLM_TIMEOUT invalid → legacy LLM_TIMEOUT (mirror of
    translate-side R1 RE-CODE lock)."""
    _build_openai_chat_env(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT", "45")
    monkeypatch.setenv("CHAT_LLM_TIMEOUT", "not_a_number")
    client = from_env_chat()
    assert _underlying_timeout(client) == pytest.approx(45.0)


def test_chat_timeout_invalid_at_both_layers_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both CHAT_LLM_TIMEOUT and LLM_TIMEOUT invalid → built-in default 60."""
    _build_openai_chat_env(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT", "also-bad")
    monkeypatch.setenv("CHAT_LLM_TIMEOUT", "not_a_number")
    client = from_env_chat()
    assert _underlying_timeout(client) == pytest.approx(60.0)


def test_chat_max_tokens_invalid_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHAT_LLM_MAX_TOKENS invalid → legacy LLM_MAX_TOKENS."""
    _build_openai_chat_env(monkeypatch)
    monkeypatch.setenv("LLM_MAX_TOKENS", "1024")
    monkeypatch.setenv("CHAT_LLM_MAX_TOKENS", "abc")
    client = from_env_chat()
    assert client.max_tokens == 1024


def test_chat_temperature_invalid_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHAT_LLM_TEMPERATURE invalid → legacy LLM_TEMPERATURE."""
    _build_openai_chat_env(monkeypatch)
    monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("CHAT_LLM_TEMPERATURE", "not_a_float")
    client = from_env_chat()
    assert client.temperature == pytest.approx(0.5)


# --- R2 Planner-directed micro-fix #2: OpenAICompatibleClient Protocol lock ---
#
# R0 + R1 already locked MockLLMClient via isinstance. R2 noted that the
# prod client (OpenAICompatibleClient) was unverified at runtime — mypy +
# indirect coverage only. Explicit isinstance checks below catch any
# future change that breaks the structural-typing contract.


def test_openai_client_implements_translate_protocol() -> None:
    from ht_lens.llm.client import TranslateLLMClient
    from ht_lens.llm.openai_compat import OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url="http://x/v1",
        model="x",
        api_key="x",
        max_tokens=2048,
        temperature=0.0,
    )
    assert isinstance(client, TranslateLLMClient)


def test_openai_client_implements_chat_protocol() -> None:
    from ht_lens.llm.client import ChatLLMClient
    from ht_lens.llm.openai_compat import OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url="http://x/v1",
        model="x",
        api_key="x",
        max_tokens=4096,
        temperature=0.2,
    )
    assert isinstance(client, ChatLLMClient)


# ---------------------------------------------------------------------------
# Phase 6e-2: fail-closed provider resolution
# ---------------------------------------------------------------------------


def test_translate_factory_raises_when_no_provider_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``LLM_PROVIDER`` / ``TRANSLATE_LLM_PROVIDER`` set → raise
    instead of silent mock fallback. This is the regression that lets
    ``ht-lens translate`` pollute the DB with mock output."""
    from ht_lens.llm.errors import LLMConfigurationError

    for key in ("LLM_PROVIDER", "TRANSLATE_LLM_PROVIDER", "CHAT_LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(LLMConfigurationError, match="No LLM provider configured"):
        from_env_translate()


def test_chat_factory_raises_when_no_provider_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ht_lens.llm.errors import LLMConfigurationError

    for key in ("LLM_PROVIDER", "TRANSLATE_LLM_PROVIDER", "CHAT_LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(LLMConfigurationError, match="No LLM provider configured"):
        from_env_chat()


def test_explicit_legacy_mock_still_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit ``LLM_PROVIDER=mock`` is honored (test opt-in)."""
    from ht_lens.llm.mock import MockLLMClient

    for key in ("TRANSLATE_LLM_PROVIDER", "CHAT_LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    t = from_env_translate()
    c = from_env_chat()
    assert isinstance(t, MockLLMClient)
    assert isinstance(c, MockLLMClient)


def test_explicit_scoped_mock_still_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """``TRANSLATE_LLM_PROVIDER=mock`` opts into mock for translate only."""
    from ht_lens.llm.mock import MockLLMClient

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("CHAT_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("TRANSLATE_LLM_PROVIDER", "mock")
    t = from_env_translate()
    assert isinstance(t, MockLLMClient)

    # CHAT_LLM_PROVIDER unset and no legacy → chat still fails closed.
    from ht_lens.llm.errors import LLMConfigurationError

    with pytest.raises(LLMConfigurationError):
        from_env_chat()


def test_empty_provider_value_treated_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LLM_PROVIDER=`` (empty) or whitespace-only must NOT silently
    select mock — debate §3 partial coverage."""
    from ht_lens.llm.errors import LLMConfigurationError

    for k in ("TRANSLATE_LLM_PROVIDER", "CHAT_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "   ")
    with pytest.raises(LLMConfigurationError):
        from_env_translate()


def test_scoped_provider_wins_over_legacy_mock_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Locks the precedence semantics flagged in debate §2:
    ``TRANSLATE_LLM_PROVIDER=openai_compat`` + ``LLM_PROVIDER=mock``
    → translate uses openai_compat (scoped wins). The shell mock pin
    does NOT prevent the scoped openai_compat from taking effect — that
    is by design (Phase 6e split semantics), but we lock it in so a
    future change doesn't quietly swap the order."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("TRANSLATE_LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("TRANSLATE_LLM_BASE_URL", "http://scoped.test/v1")
    monkeypatch.setenv("TRANSLATE_LLM_MODEL", "scoped-model")
    monkeypatch.setenv("HT_LENS_SKIP_LLM_CHECK", "1")
    t = from_env_translate()
    # Scoped openai_compat wins despite legacy mock pin.
    assert t.model_name == "scoped-model"

    # Chat falls back to legacy mock (only LLM_PROVIDER=mock is set there).
    from ht_lens.llm.mock import MockLLMClient

    c = from_env_chat()
    assert isinstance(c, MockLLMClient)
