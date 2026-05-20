"""Phase 3 — LLM_TIMEOUT env handling in ``ht_lens.llm.factory.from_env``."""

from __future__ import annotations

import pytest


def _build_openai_compat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "EMPTY")


def _underlying_timeout_seconds(client: object) -> float:
    """Pull the float timeout out of the openai SDK client. Compatible with
    both the legacy float and the newer ``httpx.Timeout`` wrappers."""
    underlying = getattr(client, "_client", None)
    assert underlying is not None
    raw = underlying.timeout
    if isinstance(raw, int | float):
        return float(raw)
    # httpx.Timeout — fall back to its read timeout
    return float(raw.read or raw.connect or raw.write or raw.pool or 0)


def test_factory_uses_default_timeout_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _build_openai_compat_env(monkeypatch)
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    from ht_lens.llm.factory import from_env

    client = from_env()
    assert _underlying_timeout_seconds(client) == pytest.approx(60.0)


def test_factory_honors_llm_timeout_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _build_openai_compat_env(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT", "180")
    from ht_lens.llm.factory import from_env

    client = from_env()
    assert _underlying_timeout_seconds(client) == pytest.approx(180.0)


def test_factory_falls_back_when_llm_timeout_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    _build_openai_compat_env(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT", "not-a-number")
    from ht_lens.llm.factory import from_env

    client = from_env()
    assert _underlying_timeout_seconds(client) == pytest.approx(60.0)
