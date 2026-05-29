"""phase 8a: chunks table + documents extractor/markdown_path (ht_lens 2.0)

ADDITIVE ONLY — the parallel-DB decision (Phase 8a plan) keeps 1.x data
untouched in the same database. This migration is allowed to do exactly
two kinds of thing and nothing else (user guardrail, verified by
``test_migration_0005_additive_only``):

  1. ``op.create_table("chunks")`` — the new 2.0 item-level unit.
  2. ``op.add_column("documents", ...)`` — ``extractor`` + ``markdown_path``.

It MUST NOT ``alter_column`` / ``drop_*`` / rename any existing 1.x table
(blocks, translations, pages, threads, messages, jobs, block_embeddings).
``chunk_translations`` and ``chunk_embeddings`` are deliberately deferred
to Phase 8b (debate §1.1 — keep the 8a blast radius minimal).

``chunks.page_idx`` is a plain int with NO FK to ``pages``: Phase 8a does
not create ``pages`` rows (their render columns are NOT NULL; the
side-by-side PDF render is Phase 8c). ``bbox_json`` stores MinerU's raw
coordinates verbatim.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # (1) additive columns on the existing documents table. SQLite ADD COLUMN
    #     with a non-null default backfills existing rows ('pymupdf'), so 1.x
    #     documents are correctly attributed without touching their data.
    op.add_column(
        "documents",
        sa.Column("extractor", sa.String(), nullable=False, server_default="pymupdf"),
    )
    op.add_column(
        "documents",
        sa.Column("markdown_path", sa.String(), nullable=True),
    )

    # (2) the new 2.0 chunks table.
    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("doc_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page_idx", sa.Integer(), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("text_level", sa.Integer(), nullable=True),
        sa.Column("bbox_json", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("text_format", sa.String(), nullable=True),
        sa.Column("img_path", sa.String(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
    )
    op.create_index("ix_chunks_doc_order", "chunks", ["doc_id", "order_idx"])


def downgrade() -> None:
    op.drop_index("ix_chunks_doc_order", table_name="chunks")
    op.drop_table("chunks")
    op.drop_column("documents", "markdown_path")
    op.drop_column("documents", "extractor")
