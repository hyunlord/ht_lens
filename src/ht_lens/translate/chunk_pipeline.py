"""Chunk-level async translation pipeline (Phase 8b).

Generalizes the Phase 7a-2 concurrency machine (``translate.pipeline``)
from blocks to chunks: N concurrent LLM calls bounded by
``Semaphore(concurrency)``, all ``AsyncSession`` access serialized through
``db_lock``, and identical source text deduped via ``pending_futures`` so
each unique ``cache_key`` triggers one LLM call (preserves the 5.66x).

Per-type dispatch (challenge):
- ``equation`` → passthrough: ``translated_text = content`` verbatim,
  ``model='passthrough'``, no LLM call (it is pure LaTeX).
- ``text`` / ``heading`` / ``table`` / ``unknown`` → translate ``content``
  through math-placeholder protection.
- ``image`` → translate ``content`` only if non-empty (chart text), plus
  ``caption`` → ``caption_translated``.
- Any caption-bearing chunk also gets its ``caption`` translated.

Math safety: every translated field is protected → translated → restored.
If the LLM drops a placeholder (``missing`` non-empty) the chunk is marked
``status='failed'`` and its content is NOT mutated (challenge §1 — no
append-comment fakery). ``cache_key`` is the full
``cache_key(content, src, tgt, model)`` 4-tuple (challenge §2).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Chunk, ChunkTranslation, Document
from ht_lens.db.session import ALEMBIC_HEAD, current_schema_version
from ht_lens.errors import SchemaVersionMismatch
from ht_lens.llm.client import TranslateLLMClient
from ht_lens.llm.errors import LLMTransientError
from ht_lens.translate import math_protect
from ht_lens.translate.cache import cache_key as make_cache_key

_PASSTHROUGH_TYPES = ("equation",)
_TRANSLATABLE_TYPES = ("text", "heading", "table", "unknown", "image")


@dataclass
class ChunkTranslateStats:
    document_id: int
    translated: int = 0
    passthrough: int = 0
    cached: int = 0
    skipped: int = 0
    failed: int = 0


class _MathLostError(Exception):
    """Internal: LLM dropped a math placeholder → mark chunk failed."""


async def translate_chunks(
    doc_id: int,
    session: AsyncSession,
    llm: TranslateLLMClient,
    *,
    concurrency: int = 7,
    max_retries: int = 3,
    retry_failed: bool = False,
) -> ChunkTranslateStats:
    """Translate all chunks of document ``doc_id`` (MinerU/2.0).

    Concurrency, cache, dedup, retry, cancellation, and final document
    status mirror ``translate.pipeline.translate_document``. Existing
    ``status='translated'`` chunks are skipped unless ``retry_failed``
    (which re-processes ``status='failed'`` only).
    """
    await _require_schema_head(session)
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"document {doc_id} not found")

    chunks = list(
        (
            await session.execute(
                select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.order_idx)
            )
        ).scalars()
    )
    stats = ChunkTranslateStats(document_id=doc_id)
    if not chunks:
        await _finalize(session, doc, stats)
        return stats

    model_name = getattr(llm, "model_name", "unknown")
    pending_cache: dict[str, str] = {}
    pending_futures: dict[str, asyncio.Future[str]] = {}
    sem = asyncio.Semaphore(concurrency)
    db_lock = asyncio.Lock()

    async def _cached_translate(text: str) -> str:
        """Translate ``text`` with run-level dedup + bounded concurrency.

        Identical source text → one LLM call (others await its future).
        ``text`` is the *unprotected* source so the cache_key matches
        across chunks (5.66x). Protection happens inside.
        """
        ck = make_cache_key(text, doc.src_lang, doc.tgt_lang, model_name)
        own: asyncio.Future[str] | None = None
        inflight: asyncio.Future[str] | None = None
        async with db_lock:
            if ck in pending_cache:
                return pending_cache[ck]
            existing = pending_futures.get(ck)
            if existing is None:
                own = asyncio.get_running_loop().create_future()
                pending_futures[ck] = own
            else:
                inflight = existing
        if inflight is not None:
            return await inflight
        assert own is not None
        try:
            result = await _translate_protected(
                llm, text, doc.src_lang, doc.tgt_lang, max_retries, sem
            )
        except BaseException as exc:
            if not own.done():
                own.set_exception(exc)
            own.exception()
            async with db_lock:
                pending_futures.pop(ck, None)
            raise
        if not own.done():
            own.set_result(result)
        async with db_lock:
            pending_cache[ck] = result
            pending_futures.pop(ck, None)
        return result

    async def _process(chunk: Chunk) -> None:
        async with db_lock:
            existing = await session.get(ChunkTranslation, chunk.id)
            if existing is not None:
                if existing.status == "translated":
                    stats.skipped += 1
                    return
                if existing.status == "failed" and not retry_failed:
                    stats.skipped += 1
                    return

        # equation → passthrough, no LLM.
        if chunk.type in _PASSTHROUGH_TYPES:
            async with db_lock:
                await _upsert(
                    session, chunk.id, chunk.content, None, "passthrough", None, "translated"
                )
                stats.passthrough += 1
            return

        try:
            # Body: translate non-empty content (image chunks usually have
            # empty content; charts carry text that we DO translate).
            body = await _cached_translate(chunk.content) if chunk.content.strip() else ""
            # Caption (image/chart/table) → separate translated field.
            caption_tr = (
                await _cached_translate(chunk.caption)
                if chunk.caption and chunk.caption.strip()
                else None
            )
        except _MathLostError:
            async with db_lock:
                await _upsert(session, chunk.id, "", None, model_name, None, "failed")
                stats.failed += 1
            return
        except Exception:
            async with db_lock:
                await _upsert(session, chunk.id, "", None, model_name, None, "failed")
                stats.failed += 1
            return

        ck = make_cache_key(chunk.content, doc.src_lang, doc.tgt_lang, model_name)
        async with db_lock:
            await _upsert(session, chunk.id, body, caption_tr, model_name, ck, "translated")
            stats.translated += 1

    tasks = [asyncio.create_task(_process(c)) for c in chunks]
    try:
        for fut in asyncio.as_completed(tasks):
            await fut
    except BaseException:
        for t in tasks:
            if not t.done():
                t.cancel()
        raise

    await _finalize(session, doc, stats)
    return stats


async def _translate_protected(
    llm: TranslateLLMClient,
    text: str,
    src: str,
    tgt: str,
    max_retries: int,
    sem: asyncio.Semaphore,
) -> str:
    """Protect math → translate (with retry) → restore. Raise ``_MathLostError``
    if the LLM dropped a placeholder."""
    # Collision guard: if the source already contains a ⟦MATHi⟧-shaped
    # token, skip protection (translate raw) to avoid restore mis-indexing.
    if math_protect.source_has_placeholder_collision(text):
        return await _retry_translate(llm, text, src, tgt, max_retries, sem)
    protected, store = math_protect.protect_math(text)
    out = await _retry_translate(llm, protected, src, tgt, max_retries, sem)
    restored, missing = math_protect.restore_math(out, store)
    if missing:
        raise _MathLostError(f"{len(missing)} math placeholder(s) lost by LLM")
    return restored


async def _retry_translate(
    llm: TranslateLLMClient,
    text: str,
    src: str,
    tgt: str,
    max_retries: int,
    sem: asyncio.Semaphore,
) -> str:
    last: LLMTransientError | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            await asyncio.sleep(2 ** (attempt - 1))
        try:
            async with sem:
                return await llm.translate(text, src, tgt)
        except LLMTransientError as exc:
            last = exc
    assert last is not None
    raise last


async def _upsert(
    session: AsyncSession,
    chunk_id: int,
    translated_text: str,
    caption_translated: str | None,
    model: str,
    cache_key: str | None,
    status: str,
) -> None:
    existing = await session.get(ChunkTranslation, chunk_id)
    now = datetime.now(UTC)
    if existing is None:
        session.add(
            ChunkTranslation(
                chunk_id=chunk_id,
                translated_text=translated_text,
                caption_translated=caption_translated,
                model=model,
                cache_key=cache_key,
                status=status,
                updated_at=now,
            )
        )
    else:
        existing.translated_text = translated_text
        existing.caption_translated = caption_translated
        existing.model = model
        existing.cache_key = cache_key
        existing.status = status
        existing.updated_at = now
    await session.commit()


async def _finalize(session: AsyncSession, doc: Document, stats: ChunkTranslateStats) -> None:
    doc.status = "partial_translated" if stats.failed > 0 else "translated"
    await session.commit()


async def _require_schema_head(session: AsyncSession) -> None:
    version = await current_schema_version(session)
    if version != ALEMBIC_HEAD:
        msg = "missing alembic_version" if version is None else f"version {version!r}"
        raise SchemaVersionMismatch(
            f"DB schema mismatch ({msg}; head={ALEMBIC_HEAD!r}). Run: uv run alembic upgrade head"
        )


__all__ = ["ChunkTranslateStats", "translate_chunks"]
