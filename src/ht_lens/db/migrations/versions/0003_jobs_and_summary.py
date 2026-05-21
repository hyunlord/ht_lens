"""phase 6d: jobs table + documents.summary + sha256 UNIQUE

Adds the background-job tracking table that drives ``POST /uploads`` →
extract → ingest → translate → summarize → done, plus per-document
``summary`` / ``summarized_at`` columns for the auto-generated abstract.

The ``documents.src_pdf_sha256`` UNIQUE index is the dedup guarantee
(debate §3 race fix): even with two concurrent uploads of the same
file the second INSERT raises ``IntegrityError`` and the router falls
back to the dedup branch.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("upload_path", sa.String(512), nullable=True),
        sa.Column("upload_filename", sa.String(256), nullable=True),
        sa.Column("upload_sha256", sa.String(64), nullable=True),
        sa.Column(
            "progress_pct",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("progress_message", sa.String(256), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_upload_sha256", "jobs", ["upload_sha256"])

    op.add_column("documents", sa.Column("summary", sa.Text, nullable=True))
    op.add_column("documents", sa.Column("summarized_at", sa.DateTime, nullable=True))

    # debate §3 race fix: dedup must be enforced at the DB layer, not just
    # the racy read-before-write in POST /uploads. SQLite NULL values are
    # treated as distinct so legacy rows without a hash still upgrade
    # cleanly; only non-null duplicates are rejected.
    op.create_index(
        "uq_documents_src_pdf_sha256",
        "documents",
        ["src_pdf_sha256"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_documents_src_pdf_sha256", table_name="documents")
    op.drop_column("documents", "summarized_at")
    op.drop_column("documents", "summary")
    op.drop_index("ix_jobs_upload_sha256", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
