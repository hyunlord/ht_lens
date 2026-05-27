"""Phase 6h-1 — backfill is per-document atomic.

Plan V2 Codex §3.4 contract: if any page in the document fails the
block-count or bbox-proximity check, the entire backfill aborts with
zero DB writes. This test seeds a 2-page document, mutates the
DB so page 2 has an extra block (forcing a mismatch when the script
re-extracts the original 2-block PDF), then asserts:

1. ``backfill_doc(... dry_run=True)`` reports ``status='abort'``.
2. ``backfill_doc(... dry_run=False)`` also reports ``status='abort'``
   and DB rows are unchanged.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import fitz  # type: ignore[import-untyped]
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory


def _build_two_page_pdf(out: Path) -> None:
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page(width=612, height=792)
        page.insert_text((80, 100), "Hello world.", fontsize=12, fontname="helv")
    doc.save(str(out))
    doc.close()


@pytest_asyncio.fixture
async def factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "backfill_atomic.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
    f = make_session_factory(engine)
    try:
        yield f
    finally:
        await engine.dispose()


async def _seed_doc_with_n_blocks_per_page(
    f: async_sessionmaker[AsyncSession],
    blocks_per_page: list[int],
) -> int:
    async with f() as session:
        doc = Document(
            filename="atomicity.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            src_pdf_sha256="a" * 64,
        )
        session.add(doc)
        await session.flush()
        for page_idx, n_blocks in enumerate(blocks_per_page, start=1):
            page = Page(
                doc_id=doc.id,
                page_num=page_idx,
                width=612.0,
                height=792.0,
                bg_image_path="/tmp/x.png",
                rotation=0,
                render_dpi=200,
                pixel_width=1700,
                pixel_height=2200,
            )
            session.add(page)
            await session.flush()
            for j in range(n_blocks):
                session.add(
                    Block(
                        page_id=page.id,
                        block_local_id=f"p{page_idx}_b{j:03d}",
                        type="text",
                        # Roughly match PDF "Hello world." position so the bbox
                        # proximity check would pass if counts matched.
                        bbox_json=json.dumps([80.0 + j * 5.0, 95.0, 200.0, 110.0]),
                        order_idx=j,
                        original_text="Hello world.",
                    )
                )
        await session.commit()
        return int(doc.id)


@pytest.mark.asyncio
async def test_backfill_aborts_doc_on_block_count_mismatch(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    from scripts.backfill_block_text import backfill_doc

    pdf = tmp_path / "two_page.pdf"
    _build_two_page_pdf(pdf)

    # Seed DB to disagree with the PDF — DB has 2 blocks per page, PDF has 1.
    # This forces the count-mismatch path on page 1 (before any bbox check),
    # which is exactly the abort branch we want to lock down.
    doc_id = await _seed_doc_with_n_blocks_per_page(factory, blocks_per_page=[2, 2])

    # Snapshot DB block count for later comparison.
    async with factory() as session:
        before_count = (await session.execute(select(Block))).scalars().all()
        before_texts = [(b.id, b.original_text) for b in before_count]

    # 1. dry-run reports abort.
    dry = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=True)
    assert dry.status == "abort", dry
    assert "mismatch" in (dry.reason or ""), dry

    # 2. apply mode also aborts without any DB write.
    applied = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=False)
    assert applied.status == "abort", applied

    async with factory() as session:
        after = [
            (b.id, b.original_text) for b in (await session.execute(select(Block))).scalars().all()
        ]
    assert after == before_texts, (
        f"DB must be untouched after abort; before={before_texts} after={after}"
    )
