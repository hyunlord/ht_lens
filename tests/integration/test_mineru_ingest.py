"""Phase 8a — MinerU ingest integration tests.

Drives ``ingest_mineru_output`` against an alembic-migrated DB and asserts:
chunk creation + structure preservation, figure copy, rollback on missing
image, no ``pages`` rows created (8a design), and 1.x data untouched.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ht_lens.db.models import Block, Chunk, Document, Page, Translation
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.errors import IngestError
from ht_lens.ingest_mineru.pipeline import ingest_mineru_output

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mineru" / "content_list_sample.json"
_REFERENCED_IMAGES = ["eq1.jpg", "fig1.jpg", "chart1.jpg", "fig2.jpg"]


@pytest.fixture
def mineru_out(tmp_path: Path) -> Path:
    """A MinerU-style output dir: content_list.json + images/ with the
    referenced figure files present (1px placeholder bytes)."""
    auto = tmp_path / "doc" / "auto"
    (auto / "images").mkdir(parents=True)
    shutil.copy2(FIXTURE, auto / "doc_content_list.json")
    (auto / "doc.md").write_text("# stub\n", encoding="utf-8")
    for name in _REFERENCED_IMAGES:
        (auto / "images" / name).write_bytes(b"\x89PNG\r\n\x1a\n")  # placeholder
    return auto / "doc_content_list.json"


async def _session(db_path: Path):  # type: ignore[no-untyped-def]
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    return engine, factory


@pytest.mark.asyncio
async def test_ingest_creates_chunks(api_db_path: Path, mineru_out: Path, tmp_path: Path) -> None:
    engine, factory = await _session(api_db_path)
    try:
        async with factory() as session:
            stats = await ingest_mineru_output(
                mineru_out,
                session,
                filename="doc7_ch.pdf",
                images_dir=mineru_out.parent / "images",
                dest_root=tmp_path / "ev2",
            )
            await session.commit()
        assert stats.chunks == 10  # 14 items - 4 chrome
        async with factory() as session:
            from sqlalchemy import func, select

            by_type = dict(
                (await session.execute(select(Chunk.type, func.count()).group_by(Chunk.type))).all()
            )
        assert by_type == {
            "heading": 1,
            "text": 3,
            "equation": 1,
            "image": 3,
            "table": 1,
            "unknown": 1,
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_preserves_structure(
    api_db_path: Path, mineru_out: Path, tmp_path: Path
) -> None:
    engine, factory = await _session(api_db_path)
    try:
        async with factory() as session:
            await ingest_mineru_output(
                mineru_out,
                session,
                filename="d.pdf",
                images_dir=mineru_out.parent / "images",
                dest_root=tmp_path / "ev2",
            )
            await session.commit()
        async with factory() as session:
            from sqlalchemy import select

            chunks = list(
                (await session.execute(select(Chunk).order_by(Chunk.order_idx))).scalars()
            )
        eq = next(c for c in chunks if c.type == "equation")
        assert eq.text_format == "latex" and eq.content.startswith("$$")
        assert json.loads(eq.bbox_json) == [149.0, 150.0, 520.0, 200.0]  # verbatim
        heading = next(c for c in chunks if c.type == "heading")
        assert heading.text_level == 2
        img = next(c for c in chunks if c.caption and "Simplex FA" in c.caption)
        assert img.type == "image"
        assert {c.page_idx for c in chunks} == {0, 1, 2}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_copies_figures_to_managed_dir(
    api_db_path: Path, mineru_out: Path, tmp_path: Path
) -> None:
    dest_root = tmp_path / "extracts_v2"
    engine, factory = await _session(api_db_path)
    try:
        async with factory() as session:
            stats = await ingest_mineru_output(
                mineru_out,
                session,
                filename="d.pdf",
                images_dir=mineru_out.parent / "images",
                dest_root=dest_root,
            )
            await session.commit()
        assert stats.images == 4  # eq1 + fig1 + chart1 + fig2
        managed = list((dest_root / str(stats.document_id) / "images").glob("*.jpg"))
        assert len(managed) == 4
        async with factory() as session:
            from sqlalchemy import select

            paths = [
                c.img_path
                for c in (
                    await session.execute(select(Chunk).where(Chunk.img_path.isnot(None)))
                ).scalars()
            ]
        assert all(p and Path(p).is_file() for p in paths)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_rolls_back_on_missing_image(
    api_db_path: Path, mineru_out: Path, tmp_path: Path
) -> None:
    # Delete one referenced image so copy fails mid-ingest.
    (mineru_out.parent / "images" / "fig1.jpg").unlink()
    dest_root = tmp_path / "extracts_v2"
    engine, factory = await _session(api_db_path)
    try:
        async with factory() as session:
            with pytest.raises(IngestError, match="referenced image missing"):
                await ingest_mineru_output(
                    mineru_out,
                    session,
                    filename="d.pdf",
                    images_dir=mineru_out.parent / "images",
                    dest_root=dest_root,
                )
        # No document, no chunks persisted.
        async with factory() as session:
            from sqlalchemy import func, select

            assert (await session.execute(select(func.count()).select_from(Document))).scalar() == 0
            assert (await session.execute(select(func.count()).select_from(Chunk))).scalar() == 0
        # No orphan managed image dir.
        assert not dest_root.exists() or not any(dest_root.iterdir())
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_creates_no_page_rows(
    api_db_path: Path, mineru_out: Path, tmp_path: Path
) -> None:
    """Phase 8a does not create pages rows (debate §2.1 — non-null cols)."""
    engine, factory = await _session(api_db_path)
    try:
        async with factory() as session:
            await ingest_mineru_output(
                mineru_out,
                session,
                filename="d.pdf",
                images_dir=mineru_out.parent / "images",
                dest_root=tmp_path / "ev2",
            )
            await session.commit()
        async with factory() as session:
            from sqlalchemy import func, select

            assert (await session.execute(select(func.count()).select_from(Page))).scalar() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ingest_marks_extractor_mineru(
    api_db_path: Path, mineru_out: Path, tmp_path: Path
) -> None:
    engine, factory = await _session(api_db_path)
    try:
        async with factory() as session:
            await ingest_mineru_output(
                mineru_out,
                session,
                filename="d.pdf",
                images_dir=mineru_out.parent / "images",
                markdown_path=mineru_out.parent / "doc.md",
                dest_root=tmp_path / "ev2",
            )
            await session.commit()
        async with factory() as session:
            from sqlalchemy import select

            doc = (await session.execute(select(Document))).scalar_one()
        assert doc.extractor == "mineru"
        assert doc.markdown_path and doc.markdown_path.endswith("doc.md")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_1x_data_untouched_by_mineru_ingest(
    api_db_path: Path, mineru_out: Path, tmp_path: Path
) -> None:
    """Seed a 1.x document (pymupdf + block + translation), ingest a MinerU
    doc into the same DB, assert the 1.x rows are byte-for-byte unchanged."""
    engine, factory = await _session(api_db_path)
    try:
        async with factory() as session:
            doc = Document(
                filename="legacy.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
            )
            session.add(doc)
            await session.flush()
            page = Page(
                doc_id=doc.id,
                page_num=1,
                width=100.0,
                height=100.0,
                bg_image_path="/x.png",
                pixel_width=200,
                pixel_height=200,
            )
            session.add(page)
            await session.flush()
            blk = Block(
                page_id=page.id,
                block_local_id="p1_b001",
                type="text",
                bbox_json="[0,0,1,1]",
                order_idx=1,
                original_text="hello",
            )
            session.add(blk)
            await session.flush()
            session.add(
                Translation(
                    block_id=blk.id,
                    translated_text="안녕",
                    model="m",
                    status="translated",
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
            legacy_doc_id, legacy_blk_id = doc.id, blk.id

        # Snapshot 1.x counts.
        from sqlalchemy import func, select

        async def counts() -> tuple[int, int, int]:
            async with factory() as s:
                b = (await s.execute(select(func.count()).select_from(Block))).scalar()
                t = (await s.execute(select(func.count()).select_from(Translation))).scalar()
                p = (await s.execute(select(func.count()).select_from(Page))).scalar()
                return int(b), int(t), int(p)

        before = await counts()

        async with factory() as session:
            await ingest_mineru_output(
                mineru_out,
                session,
                filename="mineru.pdf",
                images_dir=mineru_out.parent / "images",
                dest_root=tmp_path / "ev2",
            )
            await session.commit()

        after = await counts()
        assert before == after, f"1.x counts changed: {before} -> {after}"
        # The legacy document + its block/translation still intact.
        async with factory() as session:
            legacy = await session.get(Document, legacy_doc_id)
            assert legacy is not None and legacy.extractor == "pymupdf"
            tr = await session.get(Translation, legacy_blk_id)
            assert tr is not None and tr.translated_text == "안녕"
    finally:
        await engine.dispose()
