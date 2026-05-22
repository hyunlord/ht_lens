"""LLMClient factories — Phase 6e split.

Two scoped factories build the translate-path and chat-path clients
independently:

- ``from_env_translate()`` reads ``TRANSLATE_LLM_*`` env vars with fallback
  to legacy ``LLM_*``. Default ``max_tokens=2048`` (Phase E1 measured
  MAX=1513 + 35% margin) and ``temperature=0.0`` (factual translation).
- ``from_env_chat()`` reads ``CHAT_LLM_*`` with the same fallback.
  Default ``max_tokens=4096`` and ``temperature=0.2`` (Q&A/summarize).

``from_env()`` (Phase 2b legacy entry) remains as a thin delegation to
``from_env_translate()`` so pre-Phase-6e imports keep working. No
``DeprecationWarning`` in this phase (challenge §1-b) — defer to when a
second concrete client actually ships.

Precedence per challenge §2-c / §3-b: scoped value > legacy LLM_* > default.
Each key resolves independently. An empty/whitespace scoped value falls
through to the legacy slot rather than overriding it with garbage.
"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from ht_lens.llm.client import ChatLLMClient, LLMClient, TranslateLLMClient

_log = logging.getLogger("ht_lens.llm.factory")

# Phase 6e defaults — chosen from Phase E1 (~/llm_eval) measurements.
_TRANSLATE_DEFAULT_MAX_TOKENS = 2048
_CHAT_DEFAULT_MAX_TOKENS = 4096
_TRANSLATE_DEFAULT_TEMP = 0.0
_CHAT_DEFAULT_TEMP = 0.2
_DEFAULT_TIMEOUT = 60.0


def _resolve(scoped_key: str, legacy_key: str, default: str | None = None) -> str | None:
    """scoped > legacy > default precedence.

    Empty/whitespace-only strings are treated as "not set" so a stray
    ``TRANSLATE_LLM_MODEL=""`` does not override a working ``LLM_MODEL``
    with garbage (challenge §2-c).
    """
    v = os.environ.get(scoped_key, "").strip()
    if v:
        return v
    v = os.environ.get(legacy_key, "").strip()
    if v:
        return v
    return default


def _resolve_int(scoped: str, legacy: str, default: int) -> int:
    raw = _resolve(scoped, legacy)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning(
            "ignoring non-int env (%s=%r); falling back to %d",
            scoped if os.environ.get(scoped) else legacy,
            raw,
            default,
        )
        return default


def _resolve_float(scoped: str, legacy: str, default: float) -> float:
    raw = _resolve(scoped, legacy)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        _log.warning(
            "ignoring non-float env (%s=%r); falling back to %f",
            scoped if os.environ.get(scoped) else legacy,
            raw,
            default,
        )
        return default


def _build_client(
    *,
    provider: str,
    base_url: str | None,
    model: str | None,
    api_key: str,
    timeout: float,
    max_tokens: int,
    temperature: float,
) -> Any:
    """Construct a concrete client. Returned as ``Any`` so each factory can
    cast to either ``TranslateLLMClient`` or ``ChatLLMClient`` — all current
    implementations carry both ``translate`` and ``chat`` methods and so
    satisfy both protocols via structural typing, but mypy needs an explicit
    cast since :class:`TranslateLLMClient` and :class:`ChatLLMClient` are
    distinct types."""
    if provider == "mock":
        from ht_lens.llm.mock import MockLLMClient

        return MockLLMClient()
    if provider == "mock_fail":
        from ht_lens.llm.mock import FailMockLLMClient

        return FailMockLLMClient()
    if provider == "openai_compat":
        from ht_lens.llm.openai_compat import OpenAICompatibleClient

        if base_url is None or model is None:
            raise KeyError(
                "openai_compat provider requires base_url and model. "
                "Set TRANSLATE_LLM_BASE_URL/CHAT_LLM_BASE_URL/LLM_BASE_URL "
                "and the matching MODEL var."
            )
        return OpenAICompatibleClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=timeout,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    raise NotImplementedError(
        f"LLM provider {provider!r} is not implemented. "
        "Set LLM_PROVIDER (or TRANSLATE_LLM_PROVIDER / CHAT_LLM_PROVIDER) to "
        "one of mock, mock_fail, openai_compat."
    )


def from_env_translate() -> TranslateLLMClient:
    """Build the translate-path LLM client. ``TRANSLATE_LLM_*`` > ``LLM_*``."""
    provider = _resolve("TRANSLATE_LLM_PROVIDER", "LLM_PROVIDER", "mock") or "mock"
    base_url = _resolve("TRANSLATE_LLM_BASE_URL", "LLM_BASE_URL")
    model = _resolve("TRANSLATE_LLM_MODEL", "LLM_MODEL")
    api_key = _resolve("TRANSLATE_LLM_API_KEY", "LLM_API_KEY", "EMPTY") or "EMPTY"
    timeout = _resolve_float("TRANSLATE_LLM_TIMEOUT", "LLM_TIMEOUT", _DEFAULT_TIMEOUT)
    max_tokens = _resolve_int(
        "TRANSLATE_LLM_MAX_TOKENS", "LLM_MAX_TOKENS", _TRANSLATE_DEFAULT_MAX_TOKENS
    )
    temperature = _resolve_float(
        "TRANSLATE_LLM_TEMPERATURE", "LLM_TEMPERATURE", _TRANSLATE_DEFAULT_TEMP
    )
    client = _build_client(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return cast("TranslateLLMClient", client)


def from_env_chat() -> ChatLLMClient:
    """Build the chat-path LLM client. ``CHAT_LLM_*`` > ``LLM_*``."""
    provider = _resolve("CHAT_LLM_PROVIDER", "LLM_PROVIDER", "mock") or "mock"
    base_url = _resolve("CHAT_LLM_BASE_URL", "LLM_BASE_URL")
    model = _resolve("CHAT_LLM_MODEL", "LLM_MODEL")
    api_key = _resolve("CHAT_LLM_API_KEY", "LLM_API_KEY", "EMPTY") or "EMPTY"
    timeout = _resolve_float("CHAT_LLM_TIMEOUT", "LLM_TIMEOUT", _DEFAULT_TIMEOUT)
    max_tokens = _resolve_int("CHAT_LLM_MAX_TOKENS", "LLM_MAX_TOKENS", _CHAT_DEFAULT_MAX_TOKENS)
    temperature = _resolve_float("CHAT_LLM_TEMPERATURE", "LLM_TEMPERATURE", _CHAT_DEFAULT_TEMP)
    client = _build_client(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return cast("ChatLLMClient", client)


def from_env() -> LLMClient:
    """Legacy single-client factory — delegates to :func:`from_env_translate`.

    Preserved for backward-compatible imports. No deprecation warning in
    this phase (challenge §1-b)."""
    return from_env_translate()


__all__ = [
    "from_env",
    "from_env_chat",
    "from_env_translate",
]
