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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from ht_lens.api.deps import get_chat_concurrency
from ht_lens.api.routers import (
    blocks,
    chunk_chat,
    documents,
    jobs,
    messages,
    pages,
    reflow,
    search,
    threads,
    uploads,
)
from ht_lens.db.session import (
    ALEMBIC_HEAD,
    current_schema_version,
    make_engine,
    make_session_factory,
)
from ht_lens.dotenv_loader import load_repo_dotenv
from ht_lens.errors import SchemaVersionMismatch
from ht_lens.jobs.pipeline import mark_in_flight_jobs_failed
from ht_lens.llm.errors import LLMHealthCheckFailed
from ht_lens.llm.factory import from_env_chat, from_env_translate

_DEFAULT_DB = Path("data/ht_lens.db")
_DEFAULT_UPLOADS_DIR = Path("data/uploads")
_STATIC_DIR = Path(__file__).parent / "static"

_log = logging.getLogger("ht_lens.api")


class _RevalidatingStatic(StaticFiles):
    """StaticFiles subclass that emits ``Cache-Control: no-cache`` so
    browsers must revalidate every JS/CSS module via ETag. Without this
    header, browser heuristic caching (RFC 7234) lets stale modules mix
    with freshly-fetched ones after a deploy, breaking module-graph
    consistency (Phase 6i regression: viewer crashed with a phantom
    "applyMath not exported" SyntaxError because the browser combined
    the new block.js with a cached pre-Phase-6i render_markdown.js).
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        from collections.abc import MutableMapping
        from typing import Any

        async def _send(msg: MutableMapping[str, Any]) -> None:
            if msg.get("type") == "http.response.start":
                headers = [
                    (k, v) for (k, v) in (msg.get("headers") or []) if k.lower() != b"cache-control"
                ]
                headers.append((b"cache-control", b"no-cache"))
                msg = {**msg, "headers": headers}
            await send(msg)

        await super().__call__(scope, receive, _send)


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

    # Phase 6e: build two LLM clients — translate path and chat path —
    # via the scoped factories. The default config has both pointing at
    # the same backend, but env vars (TRANSLATE_LLM_* / CHAT_LLM_*) can
    # route them differently.
    translate_llm = from_env_translate()
    chat_llm = from_env_chat()
    if not _skip_llm_check():
        for label, client in (("translate", translate_llm), ("chat", chat_llm)):
            try:
                ok = await client.health_check()
            except LLMHealthCheckFailed:
                await engine.dispose()
                raise
            if not ok:
                await engine.dispose()
                raise LLMHealthCheckFailed(f"{label} LLM health_check returned False at startup")

    app.state.engine = engine
    app.state.session_factory = factory
    app.state.translate_llm = translate_llm
    app.state.chat_llm = chat_llm
    # Legacy alias: pre-Phase-6e code reads ``app.state.llm`` (e.g. some
    # tests, future cli scripts). Points at the translate client because
    # that is what ``from_env()`` returned historically.
    app.state.llm = translate_llm
    app.state.chat_semaphore = asyncio.Semaphore(get_chat_concurrency())

    # Phase 7a: embedding client for cross-document RAG. Init is lazy and
    # *fail-soft* — if bge-m3 can't load (e.g. fresh machine with no
    # internet, missing 2GB model download), the API still starts. Chat
    # falls back to same-doc-only context, and ``/blocks/{id}/related``
    # returns 503. Test overrides set this directly to a MockEmbedding-
    # Client. Phase 7a-3: provider selection (``RAG_DISABLED``,
    # ``EMBEDDING_PROVIDER=mock``, default ``BgeM3Client``) is centralized
    # in ``embedding/factory.from_env_embedding`` so the CLI auto-embed
    # chain and this lifespan share one decision tree.
    app.state.embedding_client = None
    try:
        from ht_lens.embedding.factory import from_env_embedding

        app.state.embedding_client = from_env_embedding()
        if app.state.embedding_client is not None:
            _log.info(
                "embedding client ready: %s (dim=%d)",
                app.state.embedding_client.model_name,
                app.state.embedding_client.dim,
            )
        else:
            _log.info("embedding disabled (RAG_DISABLED)")
    except Exception as exc:
        _log.warning("embedding client init failed; cross-doc RAG disabled: %s", exc)

    # Phase 6d: uploads directory + background-task pool + restart recovery.
    uploads_dir = _DEFAULT_UPLOADS_DIR
    if not uploads_dir.is_absolute():
        # Resolve relative to CWD just like _DEFAULT_DB.
        uploads_dir = Path.cwd() / uploads_dir
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.state.uploads_dir = uploads_dir
    app.state.background_tasks = set()
    recovered = await mark_in_flight_jobs_failed(factory)
    if recovered:
        _log.info("marked %d in-flight job(s) as failed on startup", recovered)

    try:
        yield
    finally:
        _log.info("lifespan shutdown")
        # Cancel any background upload jobs cleanly so the next start can
        # run the restart-recovery sweep without races.
        for task in list(app.state.background_tasks):
            task.cancel()
        if app.state.background_tasks:
            await asyncio.gather(*app.state.background_tasks, return_exceptions=True)
        await engine.dispose()


# Phase 6e-2: loader moved to ht_lens.dotenv_loader (shared with CLI).
# Backward-compat alias kept for existing tests/integration/test_dotenv_load.py
# which imports ``_load_repo_dotenv`` directly.
_load_repo_dotenv = load_repo_dotenv


def create_app() -> FastAPI:
    """Build the FastAPI app. Called by ``uvicorn`` and tests."""
    # Phase 6c: pull .env into os.environ BEFORE the lifespan factory runs.
    load_repo_dotenv()

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
    app.mount("/static", _RevalidatingStatic(directory=str(_STATIC_DIR)), name="static")

    app.include_router(documents.router)
    app.include_router(pages.router)
    app.include_router(threads.router)
    app.include_router(messages.router)
    app.include_router(search.router)
    app.include_router(blocks.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)
    app.include_router(reflow.router)
    app.include_router(chunk_chat.router)

    return app


__all__ = ["create_app"]
