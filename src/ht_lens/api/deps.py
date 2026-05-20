"""FastAPI dependencies — Phase 3.

Engine + session factory + LLM client are constructed in :mod:`ht_lens.api.app`
lifespan and stored on ``app.state``. Dependencies here pull them out and yield
per-request resources (a fresh ``AsyncSession``, the singleton LLM client, the
shared chat-concurrency semaphore).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.llm.client import LLMClient


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped :class:`AsyncSession`. Auto-closes on exit."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_llm_client(request: Request) -> LLMClient:
    """Return the lifespan-bound singleton :class:`LLMClient`."""
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
    "get_chat_semaphore",
    "get_llm_client",
    "get_session",
]
