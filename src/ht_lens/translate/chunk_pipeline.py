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


# Phase 8e-1: extra whole-translation re-rolls when a math placeholder is lost,
# on top of the transient-error retries in ``_retry_translate``. Kept small —
# the ASCII sentinel + system-prompt rule are the real fix, so this is just a
# net for provider nondeterminism (2 total attempts).
_MATH_LOSS_RETRIES = 1


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

    async def _cached_translate(text: str) -> tuple[str, bool]:
        """Translate ``text``; return ``(result, fresh)`` where ``fresh`` is
        True only if THIS call made a new LLM request.

        Cache order (verify-cross R1 §4 — restores 7a-2 persistent reuse):
        in-run ``pending_cache`` → DB ``chunk_translations.cache_key``
        (cross-run/cross-doc, uses ``ix_chunk_tr_cache``) → in-flight future
        → fresh LLM call. ``text`` is the *unprotected* source so cache_key
        matches across chunks/runs (5.66x). Protection happens inside.
        """
        ck = make_cache_key(text, doc.src_lang, doc.tgt_lang, model_name)
        own: asyncio.Future[str] | None = None
        inflight: asyncio.Future[str] | None = None
        async with db_lock:
            if ck in pending_cache:
                return pending_cache[ck], False
            db_hit = await _db_cache_lookup(session, ck)
            if db_hit is not None:
                pending_cache[ck] = db_hit
                return db_hit, False
            existing = pending_futures.get(ck)
            if existing is None:
                own = asyncio.get_running_loop().create_future()
                pending_futures[ck] = own
            else:
                inflight = existing
        if inflight is not None:
            return await inflight, False
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
        return result, True

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

        fresh = False
        had_text = bool(chunk.content.strip()) or bool(chunk.caption and chunk.caption.strip())
        try:
            # Body: translate non-empty content (image chunks usually have
            # empty content; charts carry text that we DO translate).
            if chunk.content.strip():
                body, body_fresh = await _cached_translate(chunk.content)
                fresh |= body_fresh
            else:
                body = ""
            # Caption (image/chart/table) → separate translated field.
            caption_tr: str | None = None
            if chunk.caption and chunk.caption.strip():
                caption_tr, cap_fresh = await _cached_translate(chunk.caption)
                fresh |= cap_fresh
        except _MathLostError:
            # All-or-nothing (debate §3): body and caption share one chunk
            # status. If EITHER loses a math placeholder (after the 8e-1
            # retries), the whole ChunkTranslation is 'failed' — a successful
            # body is discarded rather than stored next to a caption whose math
            # broke. The reflow API suppresses 'failed' rows, so a half-Korean
            # row with broken math would be worse than the English fallback.
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
            # A chunk that reused cache for all its text (no fresh LLM call)
            # counts as cached — this is the live 5.66x signal.
            if had_text and not fresh:
                stats.cached += 1
            else:
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


async def _db_cache_lookup(session: AsyncSession, ck: str) -> str | None:
    """Return a prior chunk's ``translated_text`` for this cache_key, or None.

    Cross-run/cross-document persistent reuse (verify-cross R1 §4) — the
    feature ``ix_chunk_tr_cache`` exists for. Only ``status='translated'``
    rows are reused. The stored ``cache_key`` is ``hash(content,…)`` so
    this hits for identical body content across documents."""
    row = (
        await session.execute(
            select(ChunkTranslation.translated_text)
            .where(
                ChunkTranslation.cache_key == ck,
                ChunkTranslation.status == "translated",
            )
            .limit(1)
        )
    ).first()
    return str(row[0]) if row is not None else None


async def _translate_protected(
    llm: TranslateLLMClient,
    text: str,
    src: str,
    tgt: str,
    max_retries: int,
    sem: asyncio.Semaphore,
) -> str:
    """Protect math → translate (with retry) → restore. Raise ``_MathLostError``
    if the LLM dropped a placeholder after the math-loss retries.

    Collision-robust (verify-cross R1 §4): if the source already contains a
    default ``[[MATHi]]``-shaped token, protect with a source-unique sentinel
    prefix instead of skipping protection — so real ``$math$`` in the same
    chunk is still byte-identical.

    Phase 8e-1: the ASCII sentinel (math_protect) + the placeholder-preservation
    rule (``_translate_system``) are the real fix for the 6 doc7 failures. This
    bounded math-loss retry is a cheap defensive net on top: if the provider is
    not fully deterministic at temperature 0, a transiently dropped placeholder
    recovers on a re-roll instead of falling back to English. It runs INSIDE the
    owner future (``_cached_translate``), so deduped waiters share the recovered
    result and never trigger their own retry storm (debate §3)."""
    prefix = "MATH"
    if math_protect.source_has_placeholder_collision(text):
        import hashlib

        prefix = "MATH" + hashlib.sha1(text.encode()).hexdigest()[:10].upper()
    protected, store = math_protect.protect_math(text, token_prefix=prefix)
    missing: list[int] = []
    for _attempt in range(_MATH_LOSS_RETRIES + 1):
        out = await _retry_translate(llm, protected, src, tgt, max_retries, sem)
        restored, missing = math_protect.restore_math(out, store, token_prefix=prefix)
        if not missing:
            return restored
    raise _MathLostError(
        f"{len(missing)} math placeholder(s) lost by LLM after {_MATH_LOSS_RETRIES + 1} attempt(s)"
    )


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
