"""Live translation pipeline test — requires a running sglang endpoint.

Skip automatically when LLM_BASE_URL / LLM_MODEL are not set.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.llm.openai_compat import OpenAICompatibleClient
from ht_lens.translate.pipeline import translate_document


def _live_client() -> OpenAICompatibleClient | None:
    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not model:
        return None
    return OpenAICompatibleClient(base_url=base_url, model=model)


async def _seed_db(db_path: Path) -> tuple[int, list[int]]:
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
    factory = make_session_factory(engine)
    block_ids: list[int] = []
    doc_id = -1
    async with factory() as session:
        doc = Document(
            filename="live_test.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            src_pdf_sha256="b" * 64,
        )
        session.add(doc)
        await session.flush()
        doc_id = doc.id
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
        for i, text_content in enumerate(["Hello world.", "This is a test."]):
            b = Block(
                page_id=page.id,
                block_local_id=f"b{i:03d}",
                type="text",
                bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                order_idx=i,
                original_text=text_content,
            )
            session.add(b)
            await session.flush()
            block_ids.append(b.id)
        await session.commit()
    await engine.dispose()
    return doc_id, block_ids


@pytest.mark.llm
@pytest.mark.asyncio
async def test_live_translate_produces_translated_rows(tmp_path: Path) -> None:
    client = _live_client()
    if client is None:
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set")

    db_path = tmp_path / "live.db"
    doc_id, block_ids = await _seed_db(db_path)

    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            stats = await translate_document(doc_id, session, client, max_retries=1)
        assert stats.translated == 2
        assert stats.failed == 0

        async with factory() as session:
            for bid in block_ids:
                tr = await session.get(Translation, bid)
                assert tr is not None
                assert tr.status == "translated"
                assert tr.translated_text.strip()
    finally:
        await engine.dispose()


@pytest.mark.llm
@pytest.mark.asyncio
async def test_live_second_run_all_cache_hits(tmp_path: Path) -> None:
    """Re-running translate on the same doc hits cache 100%."""
    client = _live_client()
    if client is None:
        pytest.skip("LLM_BASE_URL / LLM_MODEL not set")

    db_path = tmp_path / "live_cache.db"
    doc_id, _ = await _seed_db(db_path)

    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        # First run
        async with factory() as session:
            stats1 = await translate_document(doc_id, session, client)
        assert stats1.translated == 2

        # Second run — all blocks are translated → all skipped
        async with factory() as session:
            stats2 = await translate_document(doc_id, session, client)
        assert stats2.skipped == 2
        assert stats2.translated == 0
        assert stats2.cached == 0
    finally:
        await engine.dispose()
