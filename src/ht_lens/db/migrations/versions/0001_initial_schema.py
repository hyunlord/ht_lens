"""initial schema — 7 tables (documents, pages, blocks, translations, threads, messages)

Revision ID: 0001
Revises:
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("src_lang", sa.String(), nullable=False),
        sa.Column("tgt_lang", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "doc_id",
            sa.Integer(),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column("page_num", sa.Integer(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("bg_image_path", sa.String(), nullable=False),
        sa.Column("rotation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("render_dpi", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("pixel_width", sa.Integer(), nullable=False),
        sa.Column("pixel_height", sa.Integer(), nullable=False),
    )

    op.create_table(
        "blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "page_id",
            sa.Integer(),
            sa.ForeignKey("pages.id"),
            nullable=False,
        ),
        sa.Column("block_local_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("bbox_json", sa.String(), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("original_text", sa.String(), nullable=False),
    )

    op.create_table(
        "translations",
        sa.Column(
            "block_id",
            sa.Integer(),
            sa.ForeignKey("blocks.id"),
            primary_key=True,
        ),
        sa.Column("translated_text", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "block_id",
            sa.Integer(),
            sa.ForeignKey("blocks.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "thread_id",
            sa.Integer(),
            sa.ForeignKey("threads.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("translations")
    op.drop_table("blocks")
    op.drop_table("pages")
    op.drop_table("documents")
