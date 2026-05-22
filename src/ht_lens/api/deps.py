"""FastAPI dependencies — Phase 3 (Phase 6e split).

Engine + session factory + LLM clients are constructed in :mod:`ht_lens.api.app`
lifespan and stored on ``app.state``. Dependencies here pull them out and yield
per-request resources (a fresh ``AsyncSession``, the singleton LLM clients, the
shared chat-concurrency semaphore).

Phase 6e adds :func:`get_translate_llm_client` / :func:`get_chat_llm_client`
so routes can pick the right protocol. :func:`get_llm_client` is preserved
as a legacy alias pointing at the translate client (same singleton that
the pre-6e ``app.state.llm`` referenced).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.llm.client import ChatLLMClient, LLMClient, TranslateLLMClient


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped :class:`AsyncSession`. Auto-closes on exit."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_translate_llm_client(request: Request) -> TranslateLLMClient:
    """Return the lifespan-bound :class:`TranslateLLMClient` singleton."""
    client: TranslateLLMClient = request.app.state.translate_llm
    return client


def get_chat_llm_client(request: Request) -> ChatLLMClient:
    """Return the lifespan-bound :class:`ChatLLMClient` singleton."""
    client: ChatLLMClient = request.app.state.chat_llm
    return client


def get_llm_client(request: Request) -> LLMClient:
    """Legacy alias — returns ``app.state.llm`` which points at the
    translate client. Kept so pre-6e callers and tests using
    ``make_test_client(llm_override=...)`` continue to work without
    source changes."""
    client: LLMClient = request.app.state.llm
    return client


def get_chat_semaphore(request: Request) -> asyncio.Semaphore:
    """Return the shared chat-concurrency semaphore (default size 2)."""
    sem: asyncio.Semaphore = request.app.state.chat_semaphore
    return sem


def get_chat_concurrency() -> int:
    """Read ``LLM_CHAT_CONCURRENCY`` from env (default 2, min 1)."""
    raw = os.environ.get("LLM_CHAT_CONCURRENCY", "2")
    try:
        value = int(raw)
    except ValueError:
        value = 2
    return max(1, value)


__all__ = [
    "get_chat_concurrency",
    "get_chat_llm_client",
    "get_chat_semaphore",
    "get_llm_client",
    "get_session",
    "get_translate_llm_client",
]
