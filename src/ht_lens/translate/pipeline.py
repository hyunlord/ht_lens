"""Block-level async translation pipeline.

Phase 2b introduced the per-block ``_process_block`` flow with an in-memory
``pending_cache`` + DB cache lookup. Phase 7a-2 fixes a long-standing
sequential bug in the outer loop — the previous ``for ... await
_process_block(...)`` made the ``--concurrency`` parameter effectively
dead code despite an inner semaphore. The current implementation fans out
N concurrent LLM calls (bounded by ``Semaphore(concurrency)``) while
serializing all ``AsyncSession`` access through ``db_lock`` to match the
SQLAlchemy guidance that an ``AsyncSession`` is not safe for concurrent
use. Duplicate-text blocks are deduped via ``pending_futures`` so two
parallel tasks for the same cache_key still result in a single LLM call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.db.session import ALEMBIC_HEAD, current_schema_version
from ht_lens.errors import SchemaVersionMismatch
from ht_lens.llm.client import TranslateLLMClient
from ht_lens.llm.errors import LLMTransientError
from ht_lens.translate.cache import cache_key as make_cache_key

# Phase 6d: callback fired by the upload pipeline so jobs.progress_pct can
# reflect translate-stage progress. ``(done, total)`` — done is the count
# of blocks the pipeline has finished processing (cached + skipped +
# translated + failed combined), total is the candidate block count.
ProgressCallback = Callable[[int, int], Awaitable[None]]
# Granularity: emit at most once every ``_PROGRESS_EVERY`` blocks plus
# the final block. Per-block emission would hammer the DB on long docs.
_PROGRESS_EVERY = 10


@dataclass
class TranslateStats:
    document_id: int
    translated: int = 0
    skipped: int = 0
    failed: int = 0
    cached: int = 0


async def translate_document(
    doc_id: int,
    session: AsyncSession,
    llm: TranslateLLMClient,
    *,
    concurrency: int = 7,
    max_retries: int = 3,
    retry_failed: bool = False,
    block_types: tuple[str, ...] = ("text", "header"),
    dry_run: bool = False,
    on_progress: ProgressCallback | None = None,
) -> TranslateStats:
    """Translate all text/header blocks for document ``doc_id``.

    Blocks are translated concurrently (bounded by ``concurrency``) but all
    DB writes go through a single ``AsyncSession`` protected by ``db_lock``,
    avoiding the SQLAlchemy concurrent-session hazard. Default
    ``concurrency=7`` matches sglang's observed effective max running
    requests per data-parallel rank.

    Existing ``status='translated'`` rows are skipped unless
    ``retry_failed=True`` (which only re-processes ``status='failed'`` rows).
    Identical source texts within a single run are deduped via
    ``pending_futures`` so each unique ``cache_key`` triggers at most one
    LLM call.

    Phase 6d ``on_progress`` callback contract is preserved: ticks fire at
    every ``_PROGRESS_EVERY`` completions plus the final completion. Order
    follows task completion, not block submission order.
    """
    await _require_schema_head(session)

    doc = await session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"document {doc_id} not found")

    rows = await session.execute(
        select(Block)
        .join(Page, Block.page_id == Page.id)
        .where(Page.doc_id == doc_id)
        .order_by(Page.page_num, Block.order_idx)
    )
    blocks = list(rows.scalars())

    stats = TranslateStats(document_id=doc_id)

    if dry_run:
        return await _dry_run_stats(blocks, doc, session, llm, block_types, stats)

    pending_cache: dict[str, str] = {}
    pending_futures: dict[str, asyncio.Future[str]] = {}
    sem = asyncio.Semaphore(concurrency)
    db_lock = asyncio.Lock()

    async def bounded(block: Block) -> None:
        await _process_block(
            block,
            doc,
            session,
            llm,
            sem,
            db_lock,
            pending_cache,
            pending_futures,
            stats,
            max_retries=max_retries,
            retry_failed=retry_failed,
            block_types=block_types,
        )

    total = len(blocks)
    if total == 0:
        await _finalize_document_status(session, doc, stats)
        return stats

    tasks = [asyncio.create_task(bounded(b)) for b in blocks]
    done = 0
    try:
        for fut in asyncio.as_completed(tasks):
            await fut
            done += 1
            if on_progress is not None and (done % _PROGRESS_EVERY == 0 or done == total):
                await on_progress(done, total)
    except BaseException:
        # Cancel remaining tasks. Partial commits already in DB are kept;
        # Document.status is left unchanged so the user can resume.
        for t in tasks:
            if not t.done():
                t.cancel()
        raise

    await _finalize_document_status(session, doc, stats)
    return stats


async def _dry_run_stats(
    blocks: list[Block],
    doc: Document,
    session: AsyncSession,
    llm: TranslateLLMClient,
    block_types: tuple[str, ...],
    stats: TranslateStats,
) -> TranslateStats:
    model_name: str = getattr(llm, "model_name", "unknown")
    seen: set[str] = set()  # dedup within this dry-run pass (mirrors pending_cache)
    for block in blocks:
        if block.type not in block_types:
            stats.skipped += 1
            continue
        ck = make_cache_key(block.original_text, doc.src_lang, doc.tgt_lang, model_name)
        if ck in seen:
            stats.cached += 1
            continue
        hit = await _db_cache_lookup(session, ck)
        if hit is not None:
            stats.cached += 1
        else:
            stats.translated += 1
        seen.add(ck)
    return stats


async def _process_block(
    block: Block,
    doc: Document,
    session: AsyncSession,
    llm: TranslateLLMClient,
    sem: asyncio.Semaphore,
    db_lock: asyncio.Lock,
    pending_cache: dict[str, str],
    pending_futures: dict[str, asyncio.Future[str]],
    stats: TranslateStats,
    *,
    max_retries: int,
    retry_failed: bool,
    block_types: tuple[str, ...],
) -> None:
    if block.type not in block_types:
        stats.skipped += 1
        return

    model_name: str = getattr(llm, "model_name", "unknown")
    ck = make_cache_key(block.original_text, doc.src_lang, doc.tgt_lang, model_name)

    # ─── Phase 1: pre-checks under db_lock ───
    # Either we hit a cache and finish here, or we register an in-flight
    # future (or attach to an existing one) and release the lock.
    own_future: asyncio.Future[str] | None = None
    in_flight: asyncio.Future[str] | None = None

    async with db_lock:
        existing = await session.get(Translation, block.id)
        if existing is not None:
            if existing.status == "translated":
                stats.skipped += 1
                return
            if existing.status == "failed" and not retry_failed:
                stats.skipped += 1
                return

        now = datetime.now(UTC)

        if ck in pending_cache:
            stats.cached += 1
            await _upsert_translation(
                session,
                block.id,
                pending_cache[ck],
                f"cache-hit:{model_name}",
                ck,
                "translated",
                now,
                existing,
            )
            return

        db_hit = await _db_cache_lookup(session, ck)
        if db_hit is not None:
            cached_text, source_model = db_hit
            pending_cache[ck] = cached_text
            stats.cached += 1
            await _upsert_translation(
                session,
                block.id,
                cached_text,
                f"cache-hit:{source_model}",
                ck,
                "translated",
                now,
                existing,
            )
            return

        existing_future = pending_futures.get(ck)
        if existing_future is None:
            own_future = asyncio.get_running_loop().create_future()
            pending_futures[ck] = own_future
        else:
            in_flight = existing_future

    # ─── db_lock released ───

    if in_flight is not None:
        # Another task is already calling the LLM for this cache_key.
        try:
            translated_text = await in_flight
        except Exception:
            async with db_lock:
                stats.failed += 1
                await _upsert_translation(
                    session,
                    block.id,
                    "",
                    model_name,
                    ck,
                    "failed",
                    datetime.now(UTC),
                    await session.get(Translation, block.id),
                )
            return
        async with db_lock:
            stats.cached += 1
            await _upsert_translation(
                session,
                block.id,
                translated_text,
                f"cache-hit:{model_name}",
                ck,
                "translated",
                datetime.now(UTC),
                await session.get(Translation, block.id),
            )
        return

    # We own the future. Do the LLM call.
    assert own_future is not None
    try:
        translated_text = await _translate_with_retry(
            llm,
            block.original_text,
            doc.src_lang,
            doc.tgt_lang,
            max_retries,
            sem,
        )
    except Exception as exc:
        # LLM failure (permanent, retry-exhausted, empty response). Record
        # this block as failed and notify any future waiters so duplicate-
        # text blocks surface the same error. Do NOT re-raise: other
        # blocks must keep translating (Phase 2b contract).
        if not own_future.done():
            own_future.set_exception(exc)
        # Mark the exception as retrieved so asyncio doesn't log
        # "Future exception was never retrieved" via the event loop's
        # exception handler when no other task awaits this future
        # (e.g., no duplicate-text waiter exists). The
        # ``test_translate_no_waiter_failure_does_not_leak_future_exception``
        # test fails without this line.
        own_future.exception()
        async with db_lock:
            pending_futures.pop(ck, None)
            stats.failed += 1
            await _upsert_translation(
                session,
                block.id,
                "",
                model_name,
                ck,
                "failed",
                datetime.now(UTC),
                await session.get(Translation, block.id),
            )
        return
    except BaseException:
        # CancelledError / KeyboardInterrupt: propagate so the outer
        # as_completed loop can cancel the remaining tasks.
        async with db_lock:
            pending_futures.pop(ck, None)
        raise

    if not own_future.done():
        own_future.set_result(translated_text)

    async with db_lock:
        pending_cache[ck] = translated_text
        pending_futures.pop(ck, None)
        stats.translated += 1
        await _upsert_translation(
            session,
            block.id,
            translated_text,
            model_name,
            ck,
            "translated",
            datetime.now(UTC),
            await session.get(Translation, block.id),
        )


async def _db_cache_lookup(session: AsyncSession, ck: str) -> tuple[str, str] | None:
    """Return (translated_text, model) from any existing translation with this cache_key."""
    result = await session.execute(
        select(Translation.translated_text, Translation.model)
        .where(Translation.cache_key == ck)
        .where(Translation.cache_key.isnot(None))
        .where(Translation.status == "translated")
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return (str(row[0]), str(row[1]))


async def _upsert_translation(
    session: AsyncSession,
    block_id: int,
    translated_text: str,
    model: str,
    ck: str,
    status: str,
    now: datetime,
    existing: Translation | None,
) -> None:
    if existing is None:
        session.add(
            Translation(
                block_id=block_id,
                translated_text=translated_text,
                model=model,
                cache_key=ck,
                status=status,
                updated_at=now,
            )
        )
    else:
        existing.translated_text = translated_text
        existing.model = model
        existing.cache_key = ck
        existing.status = status
        existing.updated_at = now
    await session.commit()


async def _translate_with_retry(
    llm: TranslateLLMClient,
    text: str,
    src: str,
    tgt: str,
    max_retries: int,
    sem: asyncio.Semaphore,
) -> str:
    """Translate with exponential backoff; semaphore is held only during the
    actual LLM call, NOT during backoff sleeps, so transient errors don't
    starve other concurrent translations."""
    last_exc: LLMTransientError | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            await asyncio.sleep(2 ** (attempt - 1))  # outside sem — slot yielded
        try:
            async with sem:
                return await llm.translate(text, src, tgt)
        except LLMTransientError as exc:
            last_exc = exc
        # Non-transient exceptions (LLMPermanentError, EmptyLLMResponseError) bubble up
    assert last_exc is not None
    raise last_exc


async def _finalize_document_status(
    session: AsyncSession, doc: Document, stats: TranslateStats
) -> None:
    """Set ``Document.status`` based on terminal counts of this run.

    Counts are run-local; if the caller used ``retry_failed=False`` and there
    are still failed Translation rows from earlier runs, we still mark the
    document as ``translated`` when this run produced no failures. Phase 5/6
    will revisit if we need a fully derived view.

    Not called when ``translate_document`` is cancelled mid-run — the document
    status stays at its pre-run value so the caller can resume cleanly.
    """
    if stats.failed > 0:
        doc.status = "partial_translated"
    else:
        doc.status = "translated"
    await session.commit()


async def _require_schema_head(session: AsyncSession) -> None:
    version = await current_schema_version(session)
    if version != ALEMBIC_HEAD:
        msg_target = "missing alembic_version" if version is None else f"version {version!r}"
        raise SchemaVersionMismatch(
            f"DB schema mismatch ({msg_target}; head={ALEMBIC_HEAD!r}). "
            "Run: uv run alembic upgrade head"
        )


__all__ = ["TranslateStats", "translate_document"]
