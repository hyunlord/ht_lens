"""Phase 7a-3 — CLI translate auto-embed chain (subprocess tests).

The ``ht-lens translate`` command now backfills ``block_embeddings`` after
translation. These tests drive the CLI as a subprocess (the same surface
operators use via ``nohup ht-lens translate ...``) and verify each
contract from challenge.md V2:

- Default: auto-embed runs (test 1).
- ``--no-embed`` opts out (test 2).
- ``RAG_DISABLED=1`` skips at the factory (test 3).
- Console-script entrypoint ``ht-lens`` matches ``python -m`` (test 4).
- Idempotent rerun is clean (test 5).
- ``embed`` command picks up the same factory and refuses
  ``RAG_DISABLED`` (test 6).

Tests 7 (partial-failure-still-embeds) and 8 (init-failure-graceful)
live in ``tests/unit/test_translate_command_unit.py`` because subprocess
can't easily monkeypatch the factory.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, text

from ht_lens.db.base import Base
from ht_lens.db.models import Block, BlockEmbedding, Document, Page
from ht_lens.db.session import (
    ALEMBIC_HEAD,
    make_engine,
    make_session_factory,
)

REPO = Path(__file__).resolve().parents[2]

# Each block is ≥ 30 chars so backfill._candidate_blocks accepts it.
_BLOCKS = [
    "Phase 7a-3 auto-embed integration probe paragraph one.",
    "Phase 7a-3 auto-embed integration probe paragraph two.",
    "Phase 7a-3 auto-embed integration probe paragraph three.",
]


def _build_env(
    db_path: Path,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a subprocess env that filters the LLM/embedding/HF families.

    The plan V2 §2.2 fix: strip ``EMBEDDING_*`` / ``RAG_*`` / ``HF_*``
    in addition to the ``LLM_*`` / ``TRANSLATE_LLM_*`` / ``CHAT_LLM_*`` /
    ``OLLAMA_*`` keys the existing translate-CLI helper drops. Without
    this, an operator's shell could silently flip these tests.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            (
                "LLM_",
                "TRANSLATE_LLM_",
                "CHAT_LLM_",
                "OLLAMA_",
                "EMBEDDING_",
                "RAG_",
                "HF_",
            )
        )
    }
    env["HT_LENS_DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    if extra:
        env.update(extra)
    return env


def _setup_db_with_long_blocks(tmp_path: Path) -> tuple[Path, int]:
    """Seed one document + page + three text blocks (each ≥ 30 chars).

    Returns (db_path, doc_id).
    """
    db_path = tmp_path / "auto_embed_cli.db"
    holder: list[int] = []

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
                filename="auto_embed.pdf",
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
            for i, blk_text in enumerate(_BLOCKS):
                session.add(
                    Block(
                        page_id=page.id,
                        block_local_id=f"b{i:03d}",
                        type="text",
                        bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                        order_idx=i,
                        original_text=blk_text,
                    )
                )
            await session.commit()
            holder.append(doc.id)
        await engine.dispose()

    asyncio.run(_seed())
    return db_path, holder[0]


async def _count_embeddings(db_path: Path) -> int:
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            rows = (await session.execute(select(BlockEmbedding))).scalars().all()
            return len(rows)
    finally:
        await engine.dispose()


def _run_translate_subprocess(
    *args: str,
    db_path: Path,
    extra_env: dict[str, str] | None = None,
    use_console_script: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = (
        ["ht-lens", "translate", *args]
        if use_console_script
        else [sys.executable, "-m", "ht_lens.translate", *args]
    )
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=_build_env(db_path, extra_env),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_translate_cli_auto_embeds_with_mock_provider(tmp_path: Path) -> None:
    """Default path: ``LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock`` → 3 rows."""
    db_path, doc_id = _setup_db_with_long_blocks(tmp_path)
    proc = _run_translate_subprocess(
        "--doc-id",
        str(doc_id),
        "--concurrency",
        "2",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock", "EMBEDDING_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok:" in proc.stdout
    assert "embed: embedded=3" in proc.stdout, proc.stdout
    assert asyncio.run(_count_embeddings(db_path)) == 3


def test_translate_cli_no_embed_flag_skips_embedding(tmp_path: Path) -> None:
    """``--no-embed`` short-circuits before constructing any client."""
    db_path, doc_id = _setup_db_with_long_blocks(tmp_path)
    proc = _run_translate_subprocess(
        "--doc-id",
        str(doc_id),
        "--no-embed",
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok:" in proc.stdout
    assert "embed: skipped (--no-embed)" in proc.stdout, proc.stdout
    assert asyncio.run(_count_embeddings(db_path)) == 0


def test_translate_cli_rag_disabled_env_skips_embedding(tmp_path: Path) -> None:
    """``RAG_DISABLED=1`` makes the factory return None before any model load."""
    db_path, doc_id = _setup_db_with_long_blocks(tmp_path)
    proc = _run_translate_subprocess(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock", "RAG_DISABLED": "1"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "embed: skipped (RAG_DISABLED)" in proc.stdout, proc.stdout
    assert asyncio.run(_count_embeddings(db_path)) == 0


def test_translate_console_script_auto_embeds(tmp_path: Path) -> None:
    """The installed ``ht-lens`` entry point must behave like ``python -m``."""
    if shutil.which("ht-lens") is None:
        pytest.skip("ht-lens console script not on PATH")
    db_path, doc_id = _setup_db_with_long_blocks(tmp_path)
    proc = _run_translate_subprocess(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock", "EMBEDDING_PROVIDER": "mock"},
        use_console_script=True,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "ok:" in proc.stdout
    assert "embed: embedded=3" in proc.stdout, proc.stdout
    assert asyncio.run(_count_embeddings(db_path)) == 3


def test_translate_cli_rerun_clean_output(tmp_path: Path) -> None:
    """A second ``translate`` on the same doc must produce
    ``embed: embedded=0 skipped=3`` (idempotent backfill) and not duplicate
    rows. Codex debate §3.3."""
    db_path, doc_id = _setup_db_with_long_blocks(tmp_path)

    # First run — embeds 3.
    proc1 = _run_translate_subprocess(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock", "EMBEDDING_PROVIDER": "mock"},
    )
    assert proc1.returncode == 0, (proc1.stdout, proc1.stderr)
    assert "embed: embedded=3" in proc1.stdout
    assert asyncio.run(_count_embeddings(db_path)) == 3

    # Second run — translations already present; backfill must see all 3
    # as skipped (same source_hash). Use --retry-failed=False default so
    # translate skips all blocks.
    proc2 = _run_translate_subprocess(
        "--doc-id",
        str(doc_id),
        db_path=db_path,
        extra_env={"LLM_PROVIDER": "mock", "EMBEDDING_PROVIDER": "mock"},
    )
    assert proc2.returncode == 0, (proc2.stdout, proc2.stderr)
    assert "embed: embedded=0 skipped=3" in proc2.stdout, proc2.stdout
    assert asyncio.run(_count_embeddings(db_path)) == 3


def test_embed_command_refuses_when_rag_disabled(tmp_path: Path) -> None:
    """``ht-lens embed`` uses the same factory and bails on ``RAG_DISABLED``."""
    if shutil.which("ht-lens") is None:
        pytest.skip("ht-lens console script not on PATH")
    db_path, doc_id = _setup_db_with_long_blocks(tmp_path)
    proc = subprocess.run(
        ["ht-lens", "embed", "--doc-id", str(doc_id)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=_build_env(db_path, {"RAG_DISABLED": "1"}),
    )
    assert proc.returncode == 5, (proc.stdout, proc.stderr)
    assert "RAG_DISABLED" in proc.stderr, proc.stderr
