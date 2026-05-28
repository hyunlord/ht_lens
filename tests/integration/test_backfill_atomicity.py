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
        before_texts = [(b.id, b.original_text, b.bbox_json) for b in before_count]

    # 1. dry-run reports abort.
    dry = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=True)
    assert dry.status == "abort", dry
    assert "mismatch" in (dry.reason or ""), dry

    # 2. apply mode also aborts without any DB write.
    applied = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=False)
    assert applied.status == "abort", applied

    async with factory() as session:
        after = [
            (b.id, b.original_text, b.bbox_json)
            for b in (await session.execute(select(Block))).scalars().all()
        ]
    # Codex R2 §4 #2: assert BOTH original_text AND bbox_json untouched
    # — a regression that writes geometry only would otherwise slip past.
    assert after == before_texts, (
        f"DB must be untouched after abort (text+bbox); before={before_texts} after={after}"
    )


@pytest.mark.asyncio
async def test_backfill_aborts_when_pdf_missing_pages_db_has(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """Codex R1 §4 #1: a PDF shorter than the DB must abort, not partial-commit.

    DB has pages 1-3 worth of blocks; PDF has only page 1. The R1 fix in
    ``backfill_doc`` rejects when the PDF is missing pages that the DB has.
    """
    from scripts.backfill_block_text import backfill_doc

    # PDF: 1 page
    pdf = tmp_path / "single_page.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((80, 100), "Hello world.", fontsize=12, fontname="helv")
    doc.save(str(pdf))
    doc.close()

    # DB: 3 pages, 1 block each (matching PDF block count per page).
    doc_id = await _seed_doc_with_n_blocks_per_page(factory, blocks_per_page=[1, 1, 1])

    async with factory() as session:
        before = [
            (b.id, b.original_text, b.bbox_json)
            for b in (await session.execute(select(Block))).scalars().all()
        ]

    dry = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=True)
    assert dry.status == "abort", dry
    assert "missing" in (dry.reason or "").lower(), dry

    applied = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=False)
    assert applied.status == "abort", applied

    async with factory() as session:
        after = [
            (b.id, b.original_text, b.bbox_json)
            for b in (await session.execute(select(Block))).scalars().all()
        ]
    # Codex R2 §4 #2: lock both text and geometry.
    assert after == before, "no DB row (text+bbox) should change after a missing-page abort"


@pytest.mark.asyncio
async def test_backfill_aborts_on_bbox_drift(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """Codex R1 §4 #3: bbox center drift > 20pt aborts without writes.

    Same page + block counts, but DB block bbox is placed far from the
    PDF rendering position. ``backfill_doc`` rejects per the proximity
    check.
    """
    from scripts.backfill_block_text import backfill_doc

    pdf = tmp_path / "drift.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((80, 100), "Hello world.", fontsize=12, fontname="helv")
    doc.save(str(pdf))
    doc.close()

    # Manually seed: 1 page, 1 block at intentionally wrong bbox (center far from PDF).
    async with factory() as session:
        d = Document(
            filename="drift.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            src_pdf_sha256="b" * 64,
        )
        session.add(d)
        await session.flush()
        page_row = Page(
            doc_id=d.id,
            page_num=1,
            width=612.0,
            height=792.0,
            bg_image_path="/tmp/x.png",
            rotation=0,
            render_dpi=200,
            pixel_width=1700,
            pixel_height=2200,
        )
        session.add(page_row)
        await session.flush()
        # Block placed at bottom-right of page (PDF text is at top-left).
        session.add(
            Block(
                page_id=page_row.id,
                block_local_id="p1_b000",
                type="text",
                bbox_json=json.dumps([500.0, 700.0, 600.0, 720.0]),
                order_idx=0,
                original_text="Hello world.",
            )
        )
        await session.commit()
        doc_id = int(d.id)

    async with factory() as session:
        before = [
            (b.id, b.original_text, b.bbox_json)
            for b in (await session.execute(select(Block))).scalars().all()
        ]

    result = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=False)
    assert result.status == "abort", result
    assert "drift" in (result.reason or "").lower(), result

    async with factory() as session:
        after = [
            (b.id, b.original_text, b.bbox_json)
            for b in (await session.execute(select(Block))).scalars().all()
        ]
    # Codex R2 §4 #2: lock both text and geometry.
    assert after == before, "no DB row (text+bbox) should change after a bbox-drift abort"


@pytest.mark.asyncio
async def test_backfill_apply_succeeds_when_pdf_matches_db(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """Codex R1 §2: prove the successful apply path. PDF + DB align on
    block counts and bbox positions; backfill applies and original_text
    + bbox_json are updated in place (block_id preserved)."""
    from scripts.backfill_block_text import backfill_doc

    pdf = tmp_path / "match.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Two same-y fragments — this is the Pattern A signature, so after fix
    # the joined text should be space-separated.
    page.insert_text((80, 100), "22.4.3", fontsize=12, fontname="helv")
    page.insert_text((150, 100), "Other applications", fontsize=12, fontname="helv")
    doc.save(str(pdf))
    doc.close()

    # Sanity-check what the extractor will return so the DB seed can match
    # its bboxes within the 20pt tolerance.
    from ht_lens.extract._fitz import iter_pages, open_pdf
    from ht_lens.extract.blocks import group_page
    from ht_lens.extract.reading_order import order_blocks

    with open_pdf(pdf) as fdoc:
        raw = next(iter(iter_pages(fdoc)))
    extracted = order_blocks(group_page(raw))
    if not extracted:
        pytest.skip("PyMuPDF could not extract text from the synthetic PDF")

    async with factory() as session:
        d = Document(
            filename="match.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            src_pdf_sha256="c" * 64,
        )
        session.add(d)
        await session.flush()
        page_row = Page(
            doc_id=d.id,
            page_num=1,
            width=612.0,
            height=792.0,
            bg_image_path="/tmp/x.png",
            rotation=0,
            render_dpi=200,
            pixel_width=1700,
            pixel_height=2200,
        )
        session.add(page_row)
        await session.flush()
        # Seed DB blocks with bboxes that match the extractor and an
        # intentionally stale text format (\n) so the update is observable.
        for i, eb in enumerate(extracted):
            session.add(
                Block(
                    page_id=page_row.id,
                    block_local_id=f"p1_b{i:03d}",
                    type=eb.type,
                    bbox_json=json.dumps(list(eb.bbox)),
                    order_idx=i,
                    original_text="STALE\nTEXT",
                )
            )
        await session.commit()
        doc_id = int(d.id)
        seeded_block_ids = [b.id for b in (await session.execute(select(Block))).scalars().all()]

    result = await backfill_doc(factory, doc_id=doc_id, pdf_path=pdf, dry_run=False)
    assert result.status == "ok", result
    assert len(result.proposed) >= 1
    # Codex R2 §4 #3: lock the EXACT proposed payload (text + bbox) per
    # block so a regression that produced wrong text/bbox would fail.
    expected_by_id = {upd.block_id: (upd.new_text, list(upd.new_bbox)) for upd in result.proposed}
    extracted_by_pos = {tuple(eb.bbox): eb.text for eb in extracted}

    async with factory() as session:
        rows = (await session.execute(select(Block))).scalars().all()
        new_ids = [b.id for b in rows]
        # block_id preserved (Phase 6h-1 contract: translations / embeddings
        # remain attached to the same row).
        assert sorted(new_ids) == sorted(seeded_block_ids)
        # Stale STALE\nTEXT is replaced with extractor output.
        assert all(b.original_text != "STALE\nTEXT" for b in rows)
        # Exact payload check: every updated block's persisted text/bbox
        # matches the extractor's output and never contains a stray \n
        # for Pattern A inputs (since the synthetic PDF places fragments
        # on the same baseline).
        for b in rows:
            if b.id not in expected_by_id:
                continue
            exp_text, exp_bbox = expected_by_id[b.id]
            assert b.original_text == exp_text, (
                f"block {b.id} text mismatch: got {b.original_text!r}, expected {exp_text!r}"
            )
            persisted_bbox = json.loads(b.bbox_json)
            assert persisted_bbox == exp_bbox, (
                f"block {b.id} bbox mismatch: got {persisted_bbox}, expected {exp_bbox}"
            )
            # Pattern A property: the synthetic PDF's same-baseline
            # fragments must collapse, so no surviving newline.
            assert "\n" not in b.original_text, (
                f"block {b.id} should be Pattern-A collapsed: {b.original_text!r}"
            )
        # Sanity: the extractor saw exactly what we just persisted.
        for b in rows:
            persisted_bbox_t = tuple(json.loads(b.bbox_json))
            if persisted_bbox_t in extracted_by_pos:
                assert b.original_text == extracted_by_pos[persisted_bbox_t]
