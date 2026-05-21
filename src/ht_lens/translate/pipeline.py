"""Block-level async translation pipeline — Phase 2b."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.db.session import ALEMBIC_HEAD, current_schema_version
from ht_lens.errors import SchemaVersionMismatch
from ht_lens.llm.client import LLMClient
from ht_lens.llm.errors import LLMTransientError
from ht_lens.translate.cache import cache_key as make_cache_key


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
    llm: LLMClient,
    *,
    concurrency: int = 5,
    max_retries: int = 3,
    retry_failed: bool = False,
    block_types: tuple[str, ...] = ("text", "header"),
    dry_run: bool = False,
) -> TranslateStats:
    """Translate all text/header blocks for document ``doc_id``.

    Each block is committed individually. Image blocks are skipped.
    Existing ``status='translated'`` rows are skipped unless
    ``retry_failed=True`` (which only re-processes ``status='failed'`` rows).
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
    sem = asyncio.Semaphore(concurrency)

    for block in blocks:
        await _process_block(
            block,
            doc,
            session,
            llm,
            sem,
            pending_cache,
            stats,
            max_retries=max_retries,
            retry_failed=retry_failed,
            block_types=block_types,
        )

    # Document.status reflects the outcome of the whole translation run so the
    # API/viewer can show a meaningful state without recomputing per-block
    # joins. The pipeline only writes terminal states here; mid-run state
    # ("translating") is not exposed because translate_document is synchronous
    # from the caller's perspective.
    await _finalize_document_status(session, doc, stats)
    return stats


async def _dry_run_stats(
    blocks: list[Block],
    doc: Document,
    session: AsyncSession,
    llm: LLMClient,
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
    llm: LLMClient,
    sem: asyncio.Semaphore,
    pending_cache: dict[str, str],
    stats: TranslateStats,
    *,
    max_retries: int,
    retry_failed: bool,
    block_types: tuple[str, ...],
) -> None:
    if block.type not in block_types:
        stats.skipped += 1
        return

    existing = await session.get(Translation, block.id)
    if existing is not None:
        if existing.status == "translated":
            stats.skipped += 1
            return
        if existing.status == "failed" and not retry_failed:
            stats.skipped += 1
            return

    model_name: str = getattr(llm, "model_name", "unknown")
    ck = make_cache_key(block.original_text, doc.src_lang, doc.tgt_lang, model_name)
    now = datetime.now(UTC)

    # 1. In-memory cache (same run, dedup)
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

    # 2. DB cache lookup (cross-run)
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

    # 3. LLM call with retry
    try:
        translated_text = await _translate_with_retry(
            llm, block.original_text, doc.src_lang, doc.tgt_lang, max_retries, sem
        )
        pending_cache[ck] = translated_text
        stats.translated += 1
        await _upsert_translation(
            session, block.id, translated_text, model_name, ck, "translated", now, existing
        )
    except Exception:
        stats.failed += 1
        await _upsert_translation(session, block.id, "", model_name, ck, "failed", now, existing)


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
    llm: LLMClient,
    text: str,
    src: str,
    tgt: str,
    max_retries: int,
    sem: asyncio.Semaphore,
) -> str:
    last_exc: LLMTransientError | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            await asyncio.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s
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
