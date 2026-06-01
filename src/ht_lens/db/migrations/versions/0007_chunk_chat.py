"""phase 8d-2a: chunk_threads + chunk_messages + chunk_pins (ht_lens 2.0 chat)

ADDITIVE ONLY (same guardrail as 0005/0006). Creates the three 2.0 chat
tables. MUST NOT alter/drop any existing table (incl. the 1.x
``threads``/``messages``) — verified by
``test_chunk_chat_schema::test_migration_0007_additive_only``.

Anchor design (challenge R1/R2): a thread anchors to a concrete
``chunk_id`` for BOTH modes — ``anchor_type='chunk'`` (paragraph: that
chunk + neighbours) and ``anchor_type='section'`` (the section's HEADING
chunk; the server derives the range). This avoids ``sec_no`` ambiguity
(duplicate / unnumbered headings). Pins are a SEPARATE table, not
overloaded threads (challenge R3).

All FKs CASCADE so deleting a 2.0 document drops its threads/messages/pins.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "doc_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("anchor_type", sa.String(), nullable=False),  # 'chunk' | 'section'
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        # DB-layer guard beyond the API Literal (verify-cross R1): direct
        # migration/backfill code cannot insert an unknown anchor_type.
        sa.CheckConstraint(
            "anchor_type IN ('chunk', 'section')", name="ck_chunk_threads_anchor_type"
        ),
    )
    op.create_index("ix_chunk_threads_doc", "chunk_threads", ["doc_id"])

    op.create_table(
        "chunk_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "thread_id",
            sa.Integer(),
            sa.ForeignKey("chunk_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chunk_messages_thread", "chunk_messages", ["thread_id"])

    op.create_table(
        "chunk_pins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "doc_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chunk_pins_doc", "chunk_pins", ["doc_id"])


def downgrade() -> None:
    op.drop_index("ix_chunk_pins_doc", table_name="chunk_pins")
    op.drop_table("chunk_pins")
    op.drop_index("ix_chunk_messages_thread", table_name="chunk_messages")
    op.drop_table("chunk_messages")
    op.drop_index("ix_chunk_threads_doc", table_name="chunk_threads")
    op.drop_table("chunk_threads")
