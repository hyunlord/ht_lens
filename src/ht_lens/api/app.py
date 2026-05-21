"""FastAPI application factory — Phase 3.

``create_app()`` builds the FastAPI ``app`` with lifespan-managed engine, LLM
client, and chat-concurrency semaphore. ``app.state.skip_llm_check`` short-
circuits the startup health check (read from ``HT_LENS_SKIP_LLM_CHECK``).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ht_lens.api.deps import get_chat_concurrency
from ht_lens.api.routers import blocks, documents, messages, pages, search, threads
from ht_lens.db.session import (
    ALEMBIC_HEAD,
    current_schema_version,
    make_engine,
    make_session_factory,
)
from ht_lens.errors import SchemaVersionMismatch
from ht_lens.llm.errors import LLMHealthCheckFailed
from ht_lens.llm.factory import from_env

_DEFAULT_DB = Path("data/ht_lens.db")
_STATIC_DIR = Path(__file__).parent / "static"

_log = logging.getLogger("ht_lens.api")


def _db_path_from_env() -> Path:
    url = os.environ.get("HT_LENS_DB_URL", "")
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.removeprefix("sqlite+aiosqlite:///"))
    return _DEFAULT_DB


def _skip_llm_check() -> bool:
    return os.environ.get("HT_LENS_SKIP_LLM_CHECK", "0") in ("1", "true", "yes")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    import asyncio

    db_path = _db_path_from_env()
    _log.info("lifespan startup db_path=%s", db_path)

    engine = make_engine(db_path)
    factory = make_session_factory(engine)

    async with factory() as session:
        version = await current_schema_version(session)
    if version != ALEMBIC_HEAD:
        await engine.dispose()
        raise SchemaVersionMismatch(
            f"alembic_version={version!r} but head={ALEMBIC_HEAD!r}; "
            "run `alembic upgrade head` before starting the API"
        )

    llm = from_env()
    if not _skip_llm_check():
        try:
            ok = await llm.health_check()
        except LLMHealthCheckFailed:
            await engine.dispose()
            raise
        if not ok:
            await engine.dispose()
            raise LLMHealthCheckFailed("LLM health_check returned False at startup")

    app.state.engine = engine
    app.state.session_factory = factory
    app.state.llm = llm
    app.state.chat_semaphore = asyncio.Semaphore(get_chat_concurrency())

    try:
        yield
    finally:
        _log.info("lifespan shutdown")
        await engine.dispose()


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_repo_dotenv() -> None:
    """Load the repo-root ``.env`` into ``os.environ`` before any LLM client
    is constructed — Phase 6c fix.

    ``override=False`` keeps explicit shell exports authoritative (test
    suites can still pin ``LLM_PROVIDER=mock`` without the file overriding
    them). Looking only at the repo root avoids the CWD-vs-repo-root
    surprise raised in debate §3: a stray ``.env`` in the user's current
    document folder cannot switch the LLM provider out from under them.
    """
    dotenv = _REPO_ROOT / ".env"
    if dotenv.is_file():
        load_dotenv(dotenv_path=dotenv, override=False)


def create_app() -> FastAPI:
    """Build the FastAPI app. Called by ``uvicorn`` and tests."""
    # Phase 6c: pull .env into os.environ BEFORE the lifespan factory runs.
    _load_repo_dotenv()

    app = FastAPI(
        title="ht_lens API",
        version="0.2.0-dev",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.include_router(documents.router)
    app.include_router(pages.router)
    app.include_router(threads.router)
    app.include_router(messages.router)
    app.include_router(search.router)
    app.include_router(blocks.router)

    return app


__all__ = ["create_app"]
