"""Phase 8d-2a — migration 0007 additive-only guardrail.

0007 must add exactly the three 2.0 chat tables (chunk_threads,
chunk_messages, chunk_pins) and must NOT alter/drop any existing table —
including the 1.x ``threads``/``messages``. Compares the sqlite schema at
0006 vs 0007 (same approach as the 0005/0006 guardrail tests).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ht_lens.db.session import ALEMBIC_HEAD

REPO = Path(__file__).resolve().parents[2]

_PRE_0007_TABLES = [
    "blocks",
    "translations",
    "pages",
    "threads",
    "messages",
    "jobs",
    "block_embeddings",
    "documents",
    "chunks",
    "chunk_translations",
    "chunk_embeddings",
]
_NEW_0007_TABLES = {"chunk_threads", "chunk_messages", "chunk_pins"}


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


def test_alembic_head_is_0007() -> None:
    assert ALEMBIC_HEAD == "0007"


def test_migration_0007_additive_only(tmp_path: Path) -> None:
    db = tmp_path / "diff7.db"

    assert _alembic(db, "0006").returncode == 0
    before = _table_ddl(db)
    for t in _NEW_0007_TABLES:
        assert t not in before

    assert _alembic(db, "0007").returncode == 0
    after = _table_ddl(db)

    # Exactly the three new chat tables are added; nothing dropped.
    assert set(after) - set(before) == _NEW_0007_TABLES
    assert set(before) - set(after) == set(), "0007 dropped a pre-existing table"
    # Every pre-existing table (incl. 1.x threads/messages) is byte-identical.
    for tbl in _PRE_0007_TABLES:
        assert before.get(tbl) == after.get(tbl), f"table {tbl} DDL changed in 0007"
