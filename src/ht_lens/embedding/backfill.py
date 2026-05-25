"""Backfill ``block_embeddings`` for existing translated blocks — Phase 7a.

The backfill is **idempotent**:
- A block already at the current ``source_hash`` is skipped.
- A block whose text changed (or model bumped) is re-embedded.
- Empty / image / table / short (<30 char) blocks are skipped.

Scope per user choice: only blocks with a non-empty
``translations.translated_text`` row are considered (Phase 7a focuses on
chat-relevant text, not unindexed raw blocks from undone docs).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Block, BlockEmbedding, Page, Translation
from ht_lens.embedding.service import EmbeddingClient, text_source_hash
from ht_lens.embedding.store import upsert_embedding

_log = logging.getLogger("ht_lens.embedding.backfill")


_BACKFILL_BLOCK_TYPES = ("text", "header")
_BACKFILL_MIN_CHARS = 30


async def _candidate_blocks(session: AsyncSession, doc_id: int | None) -> list[Block]:
    """Translated blocks of type text/header with text length >= min.

    Phase 7a R1 fix (Codex verify-cross §4 #3): exclude rows where the
    translate pipeline marked ``Translation.status='failed'`` or where
    the actual Korean text is empty/whitespace. Without these guards a
    failed-translation row would still be embedded and pollute
    retrieval with garbage source content.
    """
    stmt = (
        select(Block)
        .join(Translation, Translation.block_id == Block.id)
        .join(Page, Page.id == Block.page_id)
        .where(
            Block.type.in_(_BACKFILL_BLOCK_TYPES),
            Translation.status == "translated",
            Translation.translated_text != "",
        )
        .options(selectinload(Block.page))
    )
    if doc_id is not None:
        stmt = stmt.where(Page.doc_id == doc_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [b for b in rows if len((b.original_text or "").strip()) >= _BACKFILL_MIN_CHARS]


async def backfill(
    session: AsyncSession,
    client: EmbeddingClient,
    *,
    doc_id: int | None = None,
    batch_size: int = 16,
) -> dict[str, int]:
    """Run a backfill pass; returns ``{"embedded": N, "skipped": M, "candidates": K}``.

    ``embedded`` counts blocks that produced a new or refreshed row.
    ``skipped`` counts blocks whose source_hash matched (idempotent).
    """
    candidates = await _candidate_blocks(session, doc_id)
    embedded = 0
    skipped = 0

    # Filter to needs-embed first to keep encoder batches dense.
    # Phase 7a R1 fix (Codex verify-cross §4 #4): refresh on **either**
    # a source_hash change OR a model_name change. Skipping by hash
    # alone made model swaps silently no-op despite the file claiming
    # idempotent-per-source semantics.
    needs: list[Block] = []
    expected: list[str] = []
    for blk in candidates:
        h = text_source_hash(blk.original_text)
        existing = await session.get(BlockEmbedding, blk.id)
        if (
            existing is not None
            and existing.source_hash == h
            and existing.model == client.model_name
        ):
            skipped += 1
            continue
        needs.append(blk)
        expected.append(h)

    for start in range(0, len(needs), batch_size):
        batch = needs[start : start + batch_size]
        hashes = expected[start : start + batch_size]
        texts = [b.original_text for b in batch]
        vecs = client.encode(texts)
        for blk, vec, h in zip(batch, vecs, hashes, strict=True):
            await upsert_embedding(
                session,
                block_id=blk.id,
                vector=vec,
                model=client.model_name,
                dim=client.dim,
                source_hash=h,
            )
            embedded += 1
        await session.commit()
        _log.info(
            "embedded %d/%d (doc_id=%s)",
            min(start + batch_size, len(needs)),
            len(needs),
            doc_id,
        )

    return {"candidates": len(candidates), "embedded": embedded, "skipped": skipped}


__all__ = ["backfill"]
