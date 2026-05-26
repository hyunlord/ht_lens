"""Block-vector lookup with stored-embedding reuse — Phase 7a-2.

The Phase 7a RAG path (chat_context cross-doc refs, ``/blocks/{id}/related``)
encoded the target block's text on every request, paying ~575ms of bge-m3
CPU inference even though the same vector was already sitting in
``block_embeddings``. ``get_or_encode_block_vector`` reuses the stored
vector when its ``source_hash`` matches the current text, and falls back
to a live ``encode()`` call when the row is missing or stale (e.g., the
block's source text was edited after embedding).
"""

from __future__ import annotations

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Block, BlockEmbedding
from ht_lens.embedding.service import EmbeddingClient, text_source_hash
from ht_lens.embedding.store import vector_from_bytes


async def get_or_encode_block_vector(
    session: AsyncSession,
    embedding_client: EmbeddingClient,
    block: Block,
) -> np.ndarray:
    """Return a query vector for ``block.original_text``.

    Reuses ``block_embeddings.vector`` when ``source_hash`` matches the
    current text; otherwise calls ``embedding_client.encode([text])`` and
    returns the result without caching it (caching is the job of
    ``embedding.backfill``).
    """
    text = (block.original_text or "").strip()
    if not text:
        return np.zeros((embedding_client.dim,), dtype=np.float32)

    row = await session.get(BlockEmbedding, block.id)
    if row is not None and row.source_hash == text_source_hash(text):
        return vector_from_bytes(row.vector, row.dim)

    vec: np.ndarray = embedding_client.encode([text])[0]
    return vec


__all__ = ["get_or_encode_block_vector"]
