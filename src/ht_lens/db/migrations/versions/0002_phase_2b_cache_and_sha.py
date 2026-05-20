"""phase 2b: add documents.src_pdf_sha256 and translations.cache_key

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("src_pdf_sha256", sa.String(), nullable=True))

    with op.batch_alter_table("translations") as batch_op:
        batch_op.add_column(sa.Column("cache_key", sa.String(), nullable=True))
        batch_op.create_index("ix_translations_cache_key", ["cache_key"])


def downgrade() -> None:
    with op.batch_alter_table("translations") as batch_op:
        batch_op.drop_index("ix_translations_cache_key")
        batch_op.drop_column("cache_key")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("src_pdf_sha256")
