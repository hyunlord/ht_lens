"""Subprocess tests for ``python -m ht_lens.translate`` exit codes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run_translate(
    *args: str,
    db_path: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    if db_path is not None:
        env["HT_LENS_DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "ht_lens.translate", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )


def _setup_db_with_doc(tmp_path: Path) -> tuple[Path, int]:
    """Create a minimal DB with one ingested document. Returns (db_path, doc_id)."""
    import asyncio
    import json as _json
    from datetime import UTC, datetime

    from sqlalchemy import text

    from ht_lens.db.base import Base
    from ht_lens.db.models import Block, Document, Page
    from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory

    db_path = tmp_path / "cli_test.db"
    doc_id_holder: list[int] = []

    async def _seed() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
        factory = make_session_factory(engine)
        async with factory() as session:
            doc = Document(
                filename="test.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="ready_for_translation",
                created_at=datetime.now(UTC),
                src_pdf_sha256="a" * 64,
            )
            session.add(doc)
            await session.flush()
            page = Page(
                doc_id=doc.id,
                page_num=1,
                width=595.0,
                height=842.0,
                bg_image_path="/tmp/p.png",
                rotation=0,
                render_dpi=200,
                pixel_width=1654,
                pixel_height=2339,
            )
            session.add(page)
            await session.flush()
            session.add(
                Block(
                    page_id=page.id,
                    block_local_id="b001",
                    type="text",
                    bbox_json=_json.dumps([0.0, 0.0, 100.0, 20.0]),
                    order_idx=0,
                    original_text="Hello world",
                )
            )
            await session.commit()
            doc_id_holder.append(doc.id)
        await engine.dispose()

    asyncio.run(_seed())
    return db_path, doc_id_holder[0]


def test_translate_exit_0_with_mock_llm(tmp_path: Path) -> None:
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok:" in proc.stdout


def test_translate_exit_2_on_missing_doc_id(tmp_path: Path) -> None:
    db_path, _ = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        "99999",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 2


def test_translate_dry_run_exit_0(tmp_path: Path) -> None:
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        "--dry-run",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "dry_run:" in proc.stdout


def test_translate_exit_1_on_block_failure(tmp_path: Path) -> None:
    """LLM_PROVIDER=mock_fail → every block fails → exit 1."""
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock_fail"},
    )
    assert proc.returncode == 1, (proc.stdout, proc.stderr)


def test_translate_exit_4_on_health_check_failed(tmp_path: Path) -> None:
    """Unreachable openai_compat endpoint without --dry-run → health_check fails → exit 4."""
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={
            "LLM_PROVIDER": "openai_compat",
            "LLM_BASE_URL": "http://localhost:1",
            "LLM_MODEL": "test-model",
        },
    )
    assert proc.returncode == 4, (proc.stdout, proc.stderr)


def test_translate_dry_run_bypasses_health_check(tmp_path: Path) -> None:
    """--dry-run skips health_check so an unreachable endpoint still exits 0."""
    db_path, doc_id = _setup_db_with_doc(tmp_path)
    proc = _run_translate(
        "--doc-id",
        str(doc_id),
        "--dry-run",
        db_path=db_path,
        extra_env={
            "LLM_PROVIDER": "openai_compat",
            "LLM_BASE_URL": "http://localhost:1",
            "LLM_MODEL": "test-model",
        },
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "dry_run:" in proc.stdout


def test_translate_exit_3_without_alembic_version(tmp_path: Path) -> None:
    """DB without alembic_version should give exit 3 (SchemaVersionMismatch)."""
    import asyncio

    from ht_lens.db.base import Base
    from ht_lens.db.session import make_engine

    db_path = tmp_path / "no_alembic.db"

    async def _create() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())
    proc = _run_translate(
        "--doc-id",
        "1",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 3
