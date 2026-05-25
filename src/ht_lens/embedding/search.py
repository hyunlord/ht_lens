"""Brute-force cosine similarity search over ``block_embeddings``.

The current Phase 7a corpus is ~478 blocks (only translated text/header
blocks ≥30 chars). Even at the ROADMAP scale-up target (~50K), one
``np.dot(matrix, query)`` runs in ≤50ms on a single CPU core. We avoid
the sqlite-vec / faiss dependency until a measured bottleneck demands
it (Codex debate §1).

The searcher loads embeddings on each call — no in-memory cache, no
invalidation logic. The 2MB matrix copy is cheap; SQLite is fast.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Block, Page, Translation
from ht_lens.embedding.store import load_all


@dataclass(frozen=True)
class SearchHit:
    """One result of a vector search."""

    block_id: int
    doc_id: int
    score: float  # cosine similarity in [-1, 1]; for normalized vectors typically [0, 1]


async def search(
    session: AsyncSession,
    *,
    query_vector: np.ndarray,
    top_k: int = 5,
    threshold: float = 0.5,
    exclude_doc_ids: set[int] | None = None,
    exclude_block_ids: set[int] | None = None,
    min_chars: int = 50,
) -> list[SearchHit]:
    """Return up to ``top_k`` hits with ``score >= threshold``.

    Filters applied:
    - Vectors with ``score < threshold`` are dropped.
    - Blocks whose ``doc_id`` is in ``exclude_doc_ids`` are dropped
      (Phase 7a: caller passes the target block's own doc to keep
      cross-doc semantics).
    - Blocks whose ``id`` is in ``exclude_block_ids`` are dropped.
    - Blocks shorter than ``min_chars`` characters are dropped — Codex
      debate §3: short fragments / boilerplate flood top-K otherwise.

    Empty corpus or no hits returns ``[]``.
    """
    exclude_doc_ids = exclude_doc_ids or set()
    exclude_block_ids = exclude_block_ids or set()

    ids, matrix, _ = await load_all(session)
    if matrix.shape[0] == 0:
        return []

    q = np.asarray(query_vector, dtype=np.float32).reshape(-1)
    if q.shape[0] != matrix.shape[1]:
        raise ValueError(
            f"query dim {q.shape[0]} does not match stored embeddings dim {matrix.shape[1]}"
        )
    n = float(np.linalg.norm(q))
    if n > 0:
        q = q / n

    scores = matrix @ q  # (N,) cosine similarities (vectors L2-normalized)

    # Pull candidate doc_id + length in one query so we can filter without
    # round-tripping each block.
    rows = (
        await session.execute(
            select(Block.id, Page.doc_id, Block.original_text)
            .join(Page, Page.id == Block.page_id)
            .where(Block.id.in_(ids))
        )
    ).all()
    meta = {bid: (doc_id, text or "") for bid, doc_id, text in rows}

    # Sort by score descending; apply filters lazily until we have top_k.
    order = np.argsort(-scores)  # high → low
    hits: list[SearchHit] = []
    for idx in order:
        score = float(scores[idx])
        if score < threshold:
            break  # remaining are even smaller
        bid = ids[idx]
        m = meta.get(bid)
        if m is None:
            continue
        doc_id, text = m
        if doc_id in exclude_doc_ids:
            continue
        if bid in exclude_block_ids:
            continue
        if len(text.strip()) < min_chars:
            continue
        hits.append(SearchHit(block_id=bid, doc_id=doc_id, score=score))
        if len(hits) >= top_k:
            break
    return hits


async def fetch_hit_details(
    session: AsyncSession, hits: list[SearchHit]
) -> dict[int, tuple[Block, Page, Translation | None]]:
    """Resolve hits into ``{block_id: (Block, Page, Translation|None)}``.

    Used by the API/chat-context renderer to surface previews and links
    without an N+1 query.
    """
    if not hits:
        return {}
    block_ids = [h.block_id for h in hits]
    rows = (
        (
            await session.execute(
                select(Block)
                .options(selectinload(Block.page), selectinload(Block.translation))
                .where(Block.id.in_(block_ids))
            )
        )
        .scalars()
        .all()
    )
    return {b.id: (b, b.page, b.translation) for b in rows}


__all__ = ["SearchHit", "fetch_hit_details", "search"]
