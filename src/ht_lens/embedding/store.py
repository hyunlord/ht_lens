"""Embedding storage — save/load to ``block_embeddings`` table.

Vectors are stored as raw ``numpy float32`` bytes (length ``dim * 4``).
The brute-force searcher reads ALL rows once per call via ``load_all``;
that is fine for the ~478-block Phase 7a corpus and for the ~50K block
target documented in ROADMAP. A faster index (sqlite-vec / faiss) is
deferred to a scale-up phase.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import BlockEmbedding


def vector_to_bytes(vec: np.ndarray) -> bytes:
    """Encode an L2-normalized float32 vector for BLOB storage."""
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    return v.tobytes()


def vector_from_bytes(blob: bytes, dim: int) -> np.ndarray:
    """Inverse of :func:`vector_to_bytes`. Validates the dimension."""
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.shape[0] != dim:
        raise ValueError(f"vector blob length {arr.shape[0]} does not match expected dim {dim}")
    return arr


async def upsert_embedding(
    session: AsyncSession,
    *,
    block_id: int,
    vector: np.ndarray,
    model: str,
    dim: int,
    source_hash: str,
) -> None:
    """Insert or replace the embedding row for ``block_id``."""
    stmt = sqlite_insert(BlockEmbedding).values(
        block_id=block_id,
        model=model,
        dim=dim,
        vector=vector_to_bytes(vector),
        source_hash=source_hash,
        updated_at=datetime.now(UTC),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[BlockEmbedding.block_id],
        set_={
            "model": stmt.excluded.model,
            "dim": stmt.excluded.dim,
            "vector": stmt.excluded.vector,
            "source_hash": stmt.excluded.source_hash,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)


async def load_all(session: AsyncSession) -> tuple[list[int], np.ndarray, list[str]]:
    """Load every stored embedding into one matrix.

    Returns ``(block_ids, matrix, models)`` where matrix is ``(N, dim)``
    float32 (rows L2-normalized). Empty corpus → ``([], (0, 0), [])``.
    """
    rows = (await session.execute(select(BlockEmbedding))).scalars().all()
    if not rows:
        return [], np.zeros((0, 0), dtype=np.float32), []

    # Phase 7a R1 fix (Codex verify-cross §4 #4): pick the majority dim
    # and drop outliers from BOTH the matrix AND the ids/models lists.
    # The previous loop preallocated ``len(rows)`` matrix slots and
    # appended only matching rows to ids — mismatched rows left stale
    # zero rows in the matrix, desynchronizing later
    # ``np.argsort`` → ``ids[idx]`` indexing in search.py.
    dim_counts: dict[int, int] = {}
    for row in rows:
        dim_counts[row.dim] = dim_counts.get(row.dim, 0) + 1
    target_dim = max(dim_counts, key=lambda d: dim_counts[d])

    kept_rows = [r for r in rows if r.dim == target_dim]
    matrix = np.zeros((len(kept_rows), target_dim), dtype=np.float32)
    ids: list[int] = []
    models: list[str] = []
    for i, row in enumerate(kept_rows):
        matrix[i] = vector_from_bytes(row.vector, target_dim)
        ids.append(row.block_id)
        models.append(row.model)
    return ids, matrix, models


async def get_source_hash(session: AsyncSession, block_id: int) -> str | None:
    """Return the stored ``source_hash`` for ``block_id`` (or ``None``)."""
    row = await session.get(BlockEmbedding, block_id)
    return row.source_hash if row else None


__all__ = [
    "get_source_hash",
    "load_all",
    "upsert_embedding",
    "vector_from_bytes",
    "vector_to_bytes",
]
