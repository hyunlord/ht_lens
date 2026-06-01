"""Phase 8d-2c — `ht_lens.cli translate-chunks --short-only/--chunk-id` subprocess tests.

Covers the CLI surface the challenge (R2/R8) and Codex's debate (§5 #4)
required: dry-run writes nothing, an unknown doc exits 2, an unreachable LLM
exits 4, and `--chunk-id` re-translates an explicit chunk. Exit-code contract
mirrors the sibling `translate-chunks` path (1=failed>0, 2=ValueError,
4=health-check, 5=config).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text

from ht_lens.db.base import Base
from ht_lens.db.models import Chunk, ChunkTranslation, Document
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory

REPO = Path(__file__).resolve().parents[2]


def _run(*args: str, db_path: Path, extra_env: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("LLM_", "TRANSLATE_LLM_", "CHAT_LLM_", "OLLAMA_"))
    }
    env["HT_LENS_DB_URL"] = f"sqlite+aiosqlite:///{db_path}"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "ht_lens.cli", "translate-chunks", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )


def _seed_chunk_doc(tmp_path: Path) -> tuple[Path, int, int]:
    """2.0 doc: a short 'where' (already translated) + a neighbour equation.
    Returns (db_path, doc_id, where_chunk_id)."""
    db_path = tmp_path / "chunks.db"
    holder: dict[str, int] = {}

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
        async with factory() as s:
            doc = Document(
                filename="m.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
                extractor="mineru",
            )
            s.add(doc)
            await s.flush()
            where = Chunk(
                doc_id=doc.id,
                page_idx=0,
                order_idx=0,
                type="text",
                bbox_json="[0,0,1,1]",
                content="where",
            )
            eq = Chunk(
                doc_id=doc.id,
                page_idx=0,
                order_idx=1,
                type="equation",
                bbox_json="[0,0,1,1]",
                content="$$q(z)$$",
                text_format="latex",
            )
            s.add_all([where, eq])
            await s.flush()
            s.add(
                ChunkTranslation(
                    chunk_id=where.id,
                    translated_text="[KO] where",
                    caption_translated=None,
                    model="mock",
                    cache_key="seed",
                    status="translated",
                    updated_at=datetime.now(UTC),
                )
            )
            await s.commit()
            holder["doc"] = doc.id
            holder["where"] = where.id
        await engine.dispose()

    asyncio.run(_seed())
    return db_path, holder["doc"], holder["where"]


def _read_where(db_path: Path, chunk_id: int) -> ChunkTranslation | None:
    async def _q() -> ChunkTranslation | None:
        engine = make_engine(db_path)
        factory = make_session_factory(engine)
        async with factory() as s:
            row = (
                await s.execute(
                    select(ChunkTranslation).where(ChunkTranslation.chunk_id == chunk_id)
                )
            ).scalar_one_or_none()
            # detach a plain snapshot before disposing
            snap = None
            if row is not None:
                snap = (row.translated_text, row.cache_key, row.status)
        await engine.dispose()
        return snap  # type: ignore[return-value]

    return asyncio.run(_q())


def test_short_only_dry_run_exit_0_and_no_write(tmp_path: Path) -> None:
    db_path, doc_id, where_id = _seed_chunk_doc(tmp_path)
    proc = _run(
        "--doc-id",
        str(doc_id),
        "--short-only",
        "--dry-run",
        db_path=db_path,
        extra_env={"TRANSLATE_LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "mode=dry-run" in proc.stdout
    # DB unchanged — the seed row is intact (cache_key preserved, not NULLed).
    snap = _read_where(db_path, where_id)
    assert snap == ("[KO] where", "seed", "translated")


def test_short_only_apply_exit_0_writes_null_cache_key(tmp_path: Path) -> None:
    db_path, doc_id, where_id = _seed_chunk_doc(tmp_path)
    proc = _run(
        "--doc-id",
        str(doc_id),
        "--short-only",
        db_path=db_path,
        extra_env={"TRANSLATE_LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "mode=apply" in proc.stdout
    text_, cache_key, status = _read_where(db_path, where_id)  # type: ignore[misc]
    assert text_.startswith("[KO]")
    assert cache_key is None  # R1: re-translation is not cacheable
    assert status == "translated"


def test_chunk_id_explicit_path_exit_0(tmp_path: Path) -> None:
    db_path, doc_id, where_id = _seed_chunk_doc(tmp_path)
    proc = _run(
        "--doc-id",
        str(doc_id),
        "--chunk-id",
        str(where_id),
        db_path=db_path,
        extra_env={"TRANSLATE_LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    _, cache_key, _ = _read_where(db_path, where_id)  # type: ignore[misc]
    assert cache_key is None


def test_short_only_unknown_doc_exit_2(tmp_path: Path) -> None:
    db_path, _doc_id, _ = _seed_chunk_doc(tmp_path)
    proc = _run(
        "--doc-id",
        "99999",
        "--short-only",
        db_path=db_path,
        extra_env={"TRANSLATE_LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 2, (proc.stdout, proc.stderr)


def test_short_only_llm_health_fail_exit_4(tmp_path: Path) -> None:
    db_path, doc_id, _ = _seed_chunk_doc(tmp_path)
    proc = _run(
        "--doc-id",
        str(doc_id),
        "--short-only",
        db_path=db_path,
        extra_env={
            "TRANSLATE_LLM_PROVIDER": "openai_compat",
            "TRANSLATE_LLM_BASE_URL": "http://localhost:1",
            "TRANSLATE_LLM_MODEL": "test-model",
        },
    )
    assert proc.returncode == 4, (proc.stdout, proc.stderr)


def test_dry_run_without_short_or_chunk_id_exit_2_no_write(tmp_path: Path) -> None:
    # verify-cross 8d-2c R1 defect A: --dry-run on the normal path would be
    # silently ignored and WRITE. It must fail fast (exit 2) instead, and the
    # seed row must be untouched.
    db_path, doc_id, where_id = _seed_chunk_doc(tmp_path)
    proc = _run(
        "--doc-id",
        str(doc_id),
        "--dry-run",
        db_path=db_path,
        extra_env={"TRANSLATE_LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    # Untouched: original cache_key preserved, never re-translated.
    assert _read_where(db_path, where_id) == ("[KO] where", "seed", "translated")


def test_chunk_id_unknown_exit_2(tmp_path: Path) -> None:
    # verify-cross 8d-2c R1 defect B: a nonexistent --chunk-id must exit 2,
    # not silently report candidates=0 / exit 0.
    db_path, doc_id, _ = _seed_chunk_doc(tmp_path)
    proc = _run(
        "--doc-id",
        str(doc_id),
        "--chunk-id",
        "999999",
        db_path=db_path,
        extra_env={"TRANSLATE_LLM_PROVIDER": "mock"},
    )
    assert proc.returncode == 2, (proc.stdout, proc.stderr)


def _seed_chunk_doc_at_version(tmp_path: Path, version: str) -> tuple[Path, int]:
    """Like _seed_chunk_doc but stamps a chosen alembic_version (for the
    schema-mismatch contract). Returns (db_path, doc_id)."""
    db_path = tmp_path / f"chunks_{version}.db"
    holder: dict[str, int] = {}

    async def _seed() -> None:
        engine = make_engine(db_path)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"
                )
            )
            await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{version}')"))
        factory = make_session_factory(engine)
        async with factory() as s:
            doc = Document(
                filename="m.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
                extractor="mineru",
            )
            s.add(doc)
            await s.flush()
            s.add(
                Chunk(
                    doc_id=doc.id,
                    page_idx=0,
                    order_idx=0,
                    type="text",
                    bbox_json="[0,0,1,1]",
                    content="where",
                )
            )
            await s.commit()
            holder["doc"] = doc.id
        await engine.dispose()

    asyncio.run(_seed())
    return db_path, holder["doc"]


def test_short_only_schema_mismatch_precedes_llm_health(tmp_path: Path) -> None:
    """verify-cross 8e-3 §2: on a stale (0004) DB AND an unreachable LLM, the
    schema check must win → exit 3 (SchemaVersionMismatch), NOT exit 4 (health).
    The 8e-3 reorder runs require_schema_head before from_env_translate/health."""
    db_path, doc_id = _seed_chunk_doc_at_version(tmp_path, "0004")
    proc = _run(
        "--doc-id",
        str(doc_id),
        "--short-only",
        db_path=db_path,
        extra_env={
            "TRANSLATE_LLM_PROVIDER": "openai_compat",
            "TRANSLATE_LLM_BASE_URL": "http://localhost:1",  # unreachable → would be exit 4
            "TRANSLATE_LLM_MODEL": "test-model",
        },
    )
    assert proc.returncode == 3, (proc.stdout, proc.stderr)
