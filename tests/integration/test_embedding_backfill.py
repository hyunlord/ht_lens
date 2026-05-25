"""Integration tests for the embedding backfill loop — Phase 7a."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, BlockEmbedding, Document, Page, Translation
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.backfill import backfill
from ht_lens.embedding.service import MockEmbeddingClient


@pytest_asyncio.fixture
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "backfill_test.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_doc_with_blocks(
    session: AsyncSession,
    *,
    doc_id: int = 1,
    blocks: list[tuple[str, str, bool]] | None = None,
) -> int:
    """Returns doc_id. blocks = list of (type, text, with_translation)."""
    if blocks is None:
        blocks = [
            ("text", "A long enough paragraph for backfill scope.", True),
            ("text", "Another suitably long paragraph for indexing.", True),
            ("image", "", True),  # type filter
            ("text", "short", True),  # length filter
            ("text", "Untranslated long paragraph for scope test.", False),  # translation filter
        ]
    doc = Document(
        id=doc_id,
        filename=f"d{doc_id}.pdf",
        src_lang="en",
        tgt_lang="ko",
        status="translated",
        created_at=datetime.now(UTC),
        src_pdf_sha256=f"{doc_id:064x}",
    )
    session.add(doc)
    await session.flush()
    page = Page(
        doc_id=doc_id,
        page_num=1,
        width=500.0,
        height=700.0,
        bg_image_path="/tmp/x.png",
        rotation=0,
        render_dpi=200,
        pixel_width=1000,
        pixel_height=1400,
    )
    session.add(page)
    await session.flush()
    for i, (btype, text, has_trans) in enumerate(blocks):
        blk = Block(
            page_id=page.id,
            block_local_id=f"b{i:03d}",
            type=btype,
            bbox_json=json.dumps([0.0, float(i), 100.0, float(i + 15)]),
            order_idx=i,
            original_text=text,
        )
        session.add(blk)
        await session.flush()
        if has_trans:
            session.add(
                Translation(
                    block_id=blk.id,
                    translated_text=f"[KO] {text}",
                    model="mock",
                    status="translated",
                    updated_at=datetime.now(UTC),
                )
            )
    await session.commit()
    return doc_id


@pytest.mark.asyncio
async def test_backfill_embeds_only_translated_text_or_header_with_min_length(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_factory() as session:
        await _seed_doc_with_blocks(session)

    client = MockEmbeddingClient(dim=8)
    async with db_factory() as session:
        stats = await backfill(session, client)
    # 2 text blocks pass type+length+translation filter; image/short/untranslated dropped.
    assert stats["candidates"] == 2, f"unexpected candidates: {stats}"
    assert stats["embedded"] == 2
    assert stats["skipped"] == 0

    async with db_factory() as session:
        count = (
            await session.execute(select(func.count()).select_from(BlockEmbedding))
        ).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_backfill_is_idempotent_when_source_unchanged(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_factory() as session:
        await _seed_doc_with_blocks(session)

    client = MockEmbeddingClient(dim=8)
    async with db_factory() as session:
        first = await backfill(session, client)
    async with db_factory() as session:
        second = await backfill(session, client)

    assert first["embedded"] == 2
    assert second["embedded"] == 0, "no source changed → no re-embed"
    assert second["skipped"] == 2


@pytest.mark.asyncio
async def test_backfill_refreshes_when_source_text_changes(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_factory() as session:
        await _seed_doc_with_blocks(session)

    client = MockEmbeddingClient(dim=8)
    async with db_factory() as session:
        await backfill(session, client)

    # Mutate one block's original_text.
    async with db_factory() as session:
        row = (await session.execute(select(Block).limit(1))).scalar_one()
        row.original_text = "A drastically different paragraph after edit, long enough."
        await session.commit()

    async with db_factory() as session:
        stats = await backfill(session, client)
    assert stats["embedded"] == 1
    assert stats["skipped"] == 1


@pytest.mark.asyncio
async def test_backfill_scope_filters_doc_id(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_factory() as session:
        await _seed_doc_with_blocks(
            session,
            doc_id=1,
            blocks=[
                ("text", "Doc 1 long paragraph one for backfill scope.", True),
                ("text", "Doc 1 long paragraph two for backfill scope.", True),
            ],
        )
        await _seed_doc_with_blocks(
            session,
            doc_id=2,
            blocks=[
                ("text", "Doc 2 long paragraph one for backfill scope.", True),
            ],
        )

    client = MockEmbeddingClient(dim=8)
    async with db_factory() as session:
        only_doc2 = await backfill(session, client, doc_id=2)
    assert only_doc2["candidates"] == 1
    assert only_doc2["embedded"] == 1


# ---------------------------------------------------------------------------
# Phase 7a R1 fixes — Codex verify-cross §4 missed-issues regression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_skips_failed_translations(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """R1 §4 #3 — failed translation rows must not pollute the candidate set."""
    async with db_factory() as session:
        await _seed_doc_with_blocks(
            session,
            blocks=[
                ("text", "Healthy block with translation text long enough for backfill.", True),
                ("text", "Block with FAILED translation status, long enough text here.", True),
            ],
        )
        # Mark the second block's translation as failed.
        from sqlalchemy import select as _select

        rows = (await session.execute(_select(Translation))).scalars().all()
        rows[1].status = "failed"
        rows[1].translated_text = ""
        await session.commit()

    client = MockEmbeddingClient(dim=8)
    async with db_factory() as session:
        stats = await backfill(session, client)
    assert stats["candidates"] == 1, (
        f"failed translation must be excluded; got candidates={stats['candidates']}"
    )
    assert stats["embedded"] == 1


@pytest.mark.asyncio
async def test_backfill_skips_empty_translated_text(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """R1 §4 #3 — empty translated_text rows must also be excluded."""
    async with db_factory() as session:
        await _seed_doc_with_blocks(
            session,
            blocks=[
                ("text", "Healthy block with real translation text content for backfill.", True),
                ("text", "Block with EMPTY translation text, length is fine on source.", True),
            ],
        )
        from sqlalchemy import select as _select

        rows = (await session.execute(_select(Translation))).scalars().all()
        rows[1].translated_text = ""
        await session.commit()

    client = MockEmbeddingClient(dim=8)
    async with db_factory() as session:
        stats = await backfill(session, client)
    assert stats["candidates"] == 1


@pytest.mark.asyncio
async def test_backfill_refreshes_on_model_swap(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """R1 §4 #4 — backfill must re-embed when the model_name changes,
    even if the source text (and thus source_hash) is unchanged."""
    async with db_factory() as session:
        await _seed_doc_with_blocks(session)

    client_a = MockEmbeddingClient(dim=8, model_name="model-a")
    client_b = MockEmbeddingClient(dim=8, model_name="model-b")

    async with db_factory() as session:
        first = await backfill(session, client_a)
    assert first["embedded"] == 2

    async with db_factory() as session:
        second = await backfill(session, client_b)
    # Same text → same source_hash, but model_name differs → re-embed.
    assert second["embedded"] == 2, (
        f"model swap must trigger re-embed; got embedded={second['embedded']}"
    )
    assert second["skipped"] == 0
