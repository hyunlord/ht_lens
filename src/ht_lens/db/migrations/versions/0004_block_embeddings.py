"""phase 7a: block_embeddings for cross-document RAG

Adds the ``block_embeddings`` table that stores one vector per
translated block. Vectors are produced by ``BAAI/bge-m3`` (1024-d,
multilingual) and serialized as raw ``numpy float32`` bytes
(``len == dim * 4``).

Design notes (Phase 7a plan / challenge):

- ``block_id`` is both PK and a CASCADE FK to ``blocks.id`` so deleting
  a block automatically drops its embedding.
- ``source_hash`` is the SHA-256 of the source text the vector was
  computed from. The backfill CLI compares this against the current
  block text to decide whether to re-embed (idempotent rerun).
- ``model`` + ``dim`` are kept as columns to allow future model swaps
  without losing provenance. Mixed-model rows are valid; the
  in-memory search loads them all and the caller can filter.
- ``vector`` is ``LargeBinary``; SQLite stores BLOB. brute-force search
  reads all rows once and stacks them via numpy. sqlite-vec /
  vector-index swap is deferred to a scale-up phase (50K+ blocks).

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "block_embeddings",
        sa.Column(
            "block_id",
            sa.Integer(),
            sa.ForeignKey("blocks.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_block_embeddings_model",
        "block_embeddings",
        ["model"],
    )


def downgrade() -> None:
    op.drop_index("ix_block_embeddings_model", table_name="block_embeddings")
    op.drop_table("block_embeddings")
