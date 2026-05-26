"""Phase 7a-3 — unit tests for ``translate_command`` paths that subprocess
tests can't easily reach.

Covers:
- ``test_translate_command_partial_failure_still_embeds_successful_blocks``:
  when some blocks fail translation, the successful ones must still be
  embedded (Codex debate §2.3 / §5c).
- ``test_translate_command_handles_factory_raise``: a
  ``from_env_embedding()`` call that raises (e.g., bge-m3 download fails
  on a fresh machine) must be treated as non-fatal — translate result
  drives the exit code (Codex debate §2.1, §5a; the V1 critical bug).

Both rely on the typer CliRunner against the translate sub-app so we
can monkeypatch ``from_env_embedding`` and the LLM factory without
spawning a subprocess.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text
from typer.testing import CliRunner

from ht_lens.db.base import Base
from ht_lens.db.models import (
    Block,
    BlockEmbedding,
    Document,
    Page,
    Translation,
)
from ht_lens.db.session import (
    ALEMBIC_HEAD,
    make_engine,
    make_session_factory,
)
from ht_lens.embedding.service import MockEmbeddingClient
from ht_lens.llm.errors import LLMPermanentError
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.cli import app

_LONG = "Phase 7a-3 unit-test paragraph long enough to clear the 30-char filter."


def _seed_with_n_blocks(db_path: Path, n: int) -> int:
    """Seed one doc/page/N blocks, each ≥30 chars. Returns doc_id."""
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
                filename="unit.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="ready_for_translation",
                created_at=datetime.now(UTC),
                src_pdf_sha256="u" * 64,
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
            for i in range(n):
                session.add(
                    Block(
                        page_id=page.id,
                        block_local_id=f"b{i:03d}",
                        type="text",
                        bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                        order_idx=i,
                        original_text=f"{_LONG} ({i})",
                    )
                )
            await session.commit()
            holder.append(doc.id)
        await engine.dispose()

    asyncio.run(_seed())
    return holder[0]


async def _count_embeddings(db_path: Path) -> int:
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            rows = (await session.execute(select(BlockEmbedding))).scalars().all()
            return len(rows)
    finally:
        await engine.dispose()


async def _translation_status_counts(db_path: Path) -> dict[str, int]:
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            rows = (await session.execute(select(Translation))).scalars().all()
            counts: dict[str, int] = {}
            for r in rows:
                counts[r.status] = counts.get(r.status, 0) + 1
            return counts
    finally:
        await engine.dispose()


class _PartialFailLLM(MockLLMClient):
    """Permanent failure on the FIRST input text encountered, success otherwise.

    Locks the "partial translation + auto-embed only successful blocks"
    contract from challenge.md §2.3. The mock LLM is deterministic so the
    same block (index 0) fails on every retry attempt.
    """

    model_name = "partial-fail"

    def __init__(self) -> None:
        self._fail_text: str | None = None

    async def translate(
        self,
        text: str,
        src: str,
        tgt: str,
        *,
        context: object = None,
    ) -> str:
        if self._fail_text is None:
            self._fail_text = text
        if text == self._fail_text:
            raise LLMPermanentError("partial-fail: deterministic failure on first text")
        return await super().translate(text, src, tgt, context=None)


def test_translate_command_partial_failure_still_embeds_successful_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "partial.db"
    doc_id = _seed_with_n_blocks(db_path, n=3)

    # Monkeypatch the LLM + embedding factories used by translate_command.
    # The CLI imports them lazily inside _run, so patching the module
    # attribute is enough — no need to touch sys.modules.
    monkeypatch.setattr(
        "ht_lens.llm.factory.from_env_translate",
        lambda: _PartialFailLLM(),
    )
    monkeypatch.setattr(
        "ht_lens.embedding.factory.from_env_embedding",
        lambda: MockEmbeddingClient(dim=32),
    )
    monkeypatch.setenv("HT_LENS_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    runner = CliRunner()
    result = runner.invoke(app, ["--doc-id", str(doc_id), "--concurrency", "2"])

    # Translate partial-failure → exit 1 by contract.
    assert result.exit_code == 1, (result.exit_code, result.output)
    # But embed must still run on the successful blocks.
    assert "embed: embedded=" in result.output, result.output

    # DB inspection: 1 failed + 2 translated.
    counts = asyncio.run(_translation_status_counts(db_path))
    assert counts.get("failed", 0) == 1, counts
    assert counts.get("translated", 0) == 2, counts
    # Backfill only touches status='translated' rows.
    assert asyncio.run(_count_embeddings(db_path)) == 2


def test_translate_command_handles_factory_raise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``from_env_embedding`` raising (e.g., BgeM3Client init failure on a
    fresh machine without HF cache) must NOT abort the command. Translate
    result drives the exit code; the embed branch logs a stderr warning.
    """
    db_path = tmp_path / "init_fail.db"
    doc_id = _seed_with_n_blocks(db_path, n=2)

    def _boom() -> Any:
        raise RuntimeError("simulated BgeM3Client init failure")

    monkeypatch.setattr(
        "ht_lens.llm.factory.from_env_translate",
        lambda: MockLLMClient(),
    )
    monkeypatch.setattr("ht_lens.embedding.factory.from_env_embedding", _boom)
    monkeypatch.setenv("HT_LENS_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    runner = CliRunner()
    result = runner.invoke(app, ["--doc-id", str(doc_id)])

    # Translate succeeded → exit 0 despite the embed factory raise.
    assert result.exit_code == 0, (result.exit_code, result.output)
    assert "ok:" in result.output
    assert "embed: failed (see stderr)" in result.output, result.output
    assert "auto-embed failed" in result.output, result.output
    assert "simulated BgeM3Client init failure" in result.output, result.output
    # No embeddings written.
    assert asyncio.run(_count_embeddings(db_path)) == 0
