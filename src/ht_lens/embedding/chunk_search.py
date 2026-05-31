"""Brute-force cosine similarity search over ``chunk_embeddings`` (Phase 8d-2b).

The chunk analogue of ``embedding.search`` (block path). Chunks carry
``doc_id`` directly (no Page join). Two scopes the chat uses:
- cross-doc: ``exclude_doc_ids={current}`` → related chunks from OTHER docs.
- within-section: ``within_chunk_ids={section ids}`` → top-K inside a large
  section (8d-2a degraded path → relevance-ranked).

``min_chars`` defaults to 20 (not the block path's 50) so short academic
chunks — definitions, equation labels, captions — are not dropped
(challenge R6). Never raises for the chat path: empty corpus / zero or
wrong-dim query / no hits all return ``[]`` (challenge R6).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Chunk, ChunkTranslation
from ht_lens.embedding.store import load_all_chunks


@dataclass(frozen=True)
class ChunkSearchHit:
    """One result of a chunk vector search."""

    chunk_id: int
    doc_id: int
    score: float  # cosine similarity ([0,1] for normalized vectors)


async def search_chunks(
    session: AsyncSession,
    *,
    query_vector: np.ndarray,
    top_k: int = 5,
    threshold: float = 0.5,
    within_chunk_ids: set[int] | None = None,
    exclude_doc_ids: set[int] | None = None,
    exclude_chunk_ids: set[int] | None = None,
    min_chars: int = 20,
) -> list[ChunkSearchHit]:
    """Up to ``top_k`` chunk hits with ``score >= threshold``.

    ``within_chunk_ids`` restricts candidates to a section (within-section
    top-K); ``exclude_doc_ids`` drops a document (cross-doc: pass the
    current doc). Returns ``[]`` rather than raising on empty corpus,
    zero/wrong-dim query, or no hits — the chat path must never 500."""
    exclude_doc_ids = exclude_doc_ids or set()
    exclude_chunk_ids = exclude_chunk_ids or set()

    ids, matrix, _ = await load_all_chunks(session)
    if matrix.shape[0] == 0:
        return []
    q = np.asarray(query_vector, dtype=np.float32).reshape(-1)
    if q.shape[0] != matrix.shape[1]:
        return []  # dim mismatch → no hits (graceful, not a 500; challenge R6)
    n = float(np.linalg.norm(q))
    if n == 0.0:
        return []  # zero/empty query (e.g. empty image content) → no hits
    q = q / n
    scores = matrix @ q

    rows = (
        await session.execute(
            select(Chunk.id, Chunk.doc_id, Chunk.content).where(Chunk.id.in_(ids))
        )
    ).all()
    meta = {cid: (doc_id, text or "") for cid, doc_id, text in rows}

    order = np.argsort(-scores)  # high → low
    hits: list[ChunkSearchHit] = []
    for idx in order:
        score = float(scores[idx])
        if score < threshold:
            break  # remaining are smaller
        cid = ids[idx]
        m = meta.get(cid)
        if m is None:
            continue
        doc_id, text = m
        if within_chunk_ids is not None and cid not in within_chunk_ids:
            continue
        if doc_id in exclude_doc_ids:
            continue
        if cid in exclude_chunk_ids:
            continue
        if len(text.strip()) < min_chars:
            continue
        hits.append(ChunkSearchHit(chunk_id=cid, doc_id=doc_id, score=score))
        if len(hits) >= top_k:
            break
    return hits


async def fetch_chunk_hit_details(
    session: AsyncSession, hits: list[ChunkSearchHit]
) -> dict[int, tuple[Chunk, ChunkTranslation | None]]:
    """Resolve hits into ``{chunk_id: (Chunk, ChunkTranslation|None)}`` in one query."""
    if not hits:
        return {}
    chunk_ids = [h.chunk_id for h in hits]
    rows = (
        (
            await session.execute(
                select(Chunk)
                .options(selectinload(Chunk.translation))
                .where(Chunk.id.in_(chunk_ids))
            )
        )
        .scalars()
        .all()
    )
    return {c.id: (c, c.translation) for c in rows}


__all__ = ["ChunkSearchHit", "fetch_chunk_hit_details", "search_chunks"]
