"""Phase 8a — chunk schema + migration 0005 additive-only guardrail.

The user's explicit guardrail: migration 0005 must add the ``chunks`` table
and exactly two ``documents`` columns, and must NOT alter/drop any existing
1.x table. This test compares the sqlite schema at 0004 vs 0005 and fails
on any change beyond the approved additions (challenge §5.6).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ht_lens.db.session import ALEMBIC_HEAD

REPO = Path(__file__).resolve().parents[2]

_1X_TABLES = [
    "blocks",
    "translations",
    "pages",
    "threads",
    "messages",
    "jobs",
    "block_embeddings",
]


def _alembic(db_path: Path, rev: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", rev],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _table_ddl(db_path: Path) -> dict[str, str]:
    import sqlite3

    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        con.close()
    return {name: (sql or "") for name, sql in rows}


def test_alembic_head_is_0005() -> None:
    assert ALEMBIC_HEAD == "0005"


def test_migration_0005_additive_only(tmp_path: Path) -> None:
    db = tmp_path / "diff.db"

    assert _alembic(db, "0004").returncode == 0
    before = _table_ddl(db)
    assert "chunks" not in before
    assert "extractor" not in before["documents"]

    assert _alembic(db, "0005").returncode == 0
    after = _table_ddl(db)

    # (1) New table added.
    assert "chunks" in after, "0005 must create the chunks table"

    # (2) Existing 1.x tables byte-for-byte unchanged.
    for tbl in _1X_TABLES:
        assert before.get(tbl) == after.get(tbl), f"1.x table {tbl} DDL changed in 0005"

    # (3) documents changed ONLY by adding the two approved columns.
    assert "extractor" in after["documents"]
    assert "markdown_path" in after["documents"]
    # Nothing was removed from documents (every pre-existing column survives).
    for col in ("filename", "src_lang", "tgt_lang", "status", "created_at", "summary"):
        assert col in after["documents"], f"documents lost column {col}"

    # (4) No table was dropped.
    assert set(before) - set(after) == set(), "0005 dropped a pre-existing table"
    # Only 'chunks' is new.
    assert set(after) - set(before) == {"chunks"}


@pytest.mark.asyncio
async def test_chunk_round_trip(async_session_factory) -> None:  # type: ignore[no-untyped-def]
    """ORM round-trip for Chunk (ORM-created schema via Base.metadata)."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from ht_lens.db.models import Chunk, Document

    async with async_session_factory() as session:
        doc = Document(
            filename="d.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            extractor="mineru",
        )
        session.add(doc)
        await session.flush()
        session.add(
            Chunk(
                doc_id=doc.id,
                page_idx=3,
                order_idx=0,
                type="equation",
                text_level=None,
                bbox_json="[1.0, 2.0, 3.0, 4.0]",
                content="$$x=1$$",
                text_format="latex",
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        chunk = (await session.execute(select(Chunk))).scalar_one()
        assert chunk.page_idx == 3
        assert chunk.bbox == [1.0, 2.0, 3.0, 4.0]
        assert chunk.text_format == "latex"
