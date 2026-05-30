"""Backfill ``chunk_embeddings`` for translated text/heading chunks (Phase 8b).

Mirrors ``embedding.backfill`` (block path) but over 2.0 chunks. Added
alongside — not replacing — the block backfill so 1.x RAG stays intact.

Idempotent: a chunk already at the current ``source_hash`` AND ``model``
is skipped; a model bump or content change re-embeds (matches the Phase 7a
regression fix). Scope: ``type in (text, heading)`` with a committed
translation and source ``content`` length >= 30 chars. The embedded text
is the chunk's source ``content`` (1.x parity — block path embeds
``original_text``; chunk-side Korean retrieval is revisited in 8d).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Chunk, ChunkEmbedding, ChunkTranslation
from ht_lens.embedding.service import EmbeddingClient, text_source_hash
from ht_lens.embedding.store import upsert_chunk_embedding

_log = logging.getLogger("ht_lens.embedding.chunk_backfill")

_BACKFILL_CHUNK_TYPES = ("text", "heading")
_BACKFILL_MIN_CHARS = 30


async def _candidate_chunks(session: AsyncSession, doc_id: int | None) -> list[Chunk]:
    stmt = (
        select(Chunk)
        .join(ChunkTranslation, ChunkTranslation.chunk_id == Chunk.id)
        .where(
            Chunk.type.in_(_BACKFILL_CHUNK_TYPES),
            ChunkTranslation.status == "translated",
        )
    )
    if doc_id is not None:
        stmt = stmt.where(Chunk.doc_id == doc_id)
    chunks = list((await session.execute(stmt)).scalars())
    return [c for c in chunks if len((c.content or "").strip()) >= _BACKFILL_MIN_CHARS]


async def backfill_chunks(
    session: AsyncSession,
    client: EmbeddingClient,
    *,
    doc_id: int | None = None,
    batch_size: int = 16,
) -> dict[str, int]:
    """Embed candidate chunks; returns ``{candidates, embedded, skipped}``.

    Re-embeds on source_hash change OR model change (idempotent otherwise).
    """
    candidates = await _candidate_chunks(session, doc_id)
    embedded = 0
    skipped = 0

    needs: list[Chunk] = []
    expected: list[str] = []
    for c in candidates:
        h = text_source_hash(c.content)
        existing = await session.get(ChunkEmbedding, c.id)
        if (
            existing is not None
            and existing.source_hash == h
            and existing.model == client.model_name
        ):
            skipped += 1
            continue
        needs.append(c)
        expected.append(h)

    for start in range(0, len(needs), batch_size):
        batch = needs[start : start + batch_size]
        hashes = expected[start : start + batch_size]
        vecs = client.encode([c.content for c in batch])
        for c, vec, h in zip(batch, vecs, hashes, strict=True):
            await upsert_chunk_embedding(
                session,
                chunk_id=c.id,
                vector=vec,
                model=client.model_name,
                dim=client.dim,
                source_hash=h,
            )
            embedded += 1
        await session.commit()
        _log.info(
            "embedded %d/%d chunks (doc_id=%s)",
            min(start + batch_size, len(needs)),
            len(needs),
            doc_id,
        )

    return {"candidates": len(candidates), "embedded": embedded, "skipped": skipped}


__all__ = ["backfill_chunks"]
