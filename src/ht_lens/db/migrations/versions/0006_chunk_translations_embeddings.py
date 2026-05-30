"""phase 8b: chunk_translations + chunk_embeddings (ht_lens 2.0)

ADDITIVE ONLY (same guardrail as 0005). Creates the two 2.0 tables that
8a deliberately deferred (debate §1.1). MUST NOT alter/drop any existing
table — verified by ``test_chunk_schema::test_migration_0006_additive_only``.

Both tables CASCADE on their ``chunks`` FK so deleting a 2.0 document
(cascade → chunks) drops translations + embeddings with it.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_translations",
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("caption_translated", sa.Text(), nullable=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("cache_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chunk_tr_cache", "chunk_translations", ["cache_key"])

    op.create_table(
        "chunk_embeddings",
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
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
    op.create_index("ix_chunk_embeddings_model", "chunk_embeddings", ["model"])


def downgrade() -> None:
    op.drop_index("ix_chunk_embeddings_model", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")
    op.drop_index("ix_chunk_tr_cache", table_name="chunk_translations")
    op.drop_table("chunk_translations")
