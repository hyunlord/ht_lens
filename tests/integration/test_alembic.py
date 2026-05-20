"""Integration tests for Alembic migration: upgrade head creates expected schema."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ht_lens.db.session import (
    ALEMBIC_HEAD,
    current_schema_version,
    make_engine,
    make_session_factory,
)

REPO = Path(__file__).resolve().parents[2]


def _run_alembic_upgrade(db_path: Path) -> subprocess.CompletedProcess[str]:
    env = {"HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"}
    import os

    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=full_env,
    )


def test_alembic_upgrade_head_exits_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "test_alembic.db"
    proc = _run_alembic_upgrade(db_path)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)


def test_alembic_upgrade_head_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test_alembic.db"
    proc = _run_alembic_upgrade(db_path)
    assert proc.returncode == 0, (proc.stderr,)

    import asyncio

    engine = make_engine(db_path)

    async def _get_tables() -> list[str]:
        async with engine.connect() as conn:
            from sqlalchemy import text

            rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            return [r[0] for r in rows.fetchall()]

    tables = asyncio.run(_get_tables())
    asyncio.run(engine.dispose())

    expected = {
        "documents",
        "pages",
        "blocks",
        "translations",
        "threads",
        "messages",
        "alembic_version",
    }
    assert expected.issubset(set(tables)), f"missing tables: {expected - set(tables)}"


@pytest.mark.asyncio
async def test_current_schema_version_returns_head_after_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "test_ver.db"
    proc = _run_alembic_upgrade(db_path)
    assert proc.returncode == 0, (proc.stderr,)

    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            version = await current_schema_version(session)
        assert version == ALEMBIC_HEAD
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_current_schema_version_returns_none_for_fresh_engine(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            version = await current_schema_version(session)
        assert version is None
    finally:
        await engine.dispose()


def test_upgrade_0001_to_0002_preserves_existing_documents(tmp_path: Path) -> None:
    """Upgrade from 0001 to 0002 keeps existing rows intact."""
    import asyncio

    from sqlalchemy import text as sa_text

    db_path = tmp_path / "upgrade_test.db"

    # Upgrade to 0001 first
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0001"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env={**__import__("os").environ, "HT_LENS_DB_URL": f"sqlite+aiosqlite:///{db_path}"},
    )
    assert proc.returncode == 0, (proc.stderr,)

    # Insert a document at schema 0001
    async def _insert() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.execute(
                sa_text(
                    "INSERT INTO documents (filename, src_lang, tgt_lang, status, created_at) "
                    "VALUES ('test.pdf', 'en', 'ko', 'ready', '2026-01-01 00:00:00')"
                )
            )
        await engine.dispose()

    asyncio.run(_insert())

    # Upgrade to head (0002)
    proc2 = _run_alembic_upgrade(db_path)
    assert proc2.returncode == 0, (proc2.stderr,)

    # Verify document survived and new columns exist with NULL values
    async def _check() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            rows = await conn.execute(sa_text("SELECT filename, src_pdf_sha256 FROM documents"))
            result = rows.fetchall()
            assert len(result) == 1
            assert result[0][0] == "test.pdf"
            assert result[0][1] is None  # new nullable column defaults to NULL
        await engine.dispose()

    asyncio.run(_check())
