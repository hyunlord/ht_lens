"""Integration tests for ingest_extract_dir — happy paths and error paths."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Message, Thread, Translation
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.errors import DocumentAlreadyIngested, IngestError, SchemaVersionMismatch
from ht_lens.ingest.pipeline import ingest_extract_dir

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_extract_dir(
    tmp_path: Path,
    *,
    filename: str = "test.pdf",
    num_pages: int = 1,
    lang_guess: str = "en",
    blocks_per_page: int = 2,
    write_pngs: bool = True,
    declare_num_pages: int | None = None,
) -> Path:
    """Build a minimal but valid Phase 1 extract directory under *tmp_path*."""
    d = tmp_path / "extract"
    d.mkdir(parents=True, exist_ok=True)
    pages_dir = d / "pages"
    pages_dir.mkdir(exist_ok=True)

    declared = declare_num_pages if declare_num_pages is not None else num_pages
    meta = {
        "filename": filename,
        "num_pages": declared,
        "lang_guess": lang_guess,
        "src_pdf_sha256": "a" * 64,
        "extracted_at": "2025-01-01T00:00:00+00:00",
        "extractor_version": "1.0.0",
    }
    (d / "doc_meta.json").write_text(json.dumps(meta))

    for i in range(1, num_pages + 1):
        page = {
            "page_num": i,
            "width": 595.0,
            "height": 842.0,
            "rotation": 0,
            "render": {"dpi": 200, "pixel_width": 1654, "pixel_height": 2339, "scale": 2.778},
            "unit": "pt",
            "blocks": [
                {
                    "id": f"p{i}_b{j:03d}",
                    "type": "text",
                    "bbox": [10.0, 10.0 * j, 200.0, 30.0 * j],
                    "order": j - 1,
                    "text": f"page {i} block {j}",
                }
                for j in range(1, blocks_per_page + 1)
            ],
        }
        (pages_dir / f"page_{i:04d}.json").write_text(json.dumps(page))
        if write_pngs:
            (pages_dir / f"page_{i:04d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    return d


@pytest_asyncio.fixture
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory with ORM schema + seeded alembic_version = ALEMBIC_HEAD."""
    db_path = tmp_path / "ingest_test.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await conn.execute(text(f"INSERT INTO alembic_version VALUES ('{ALEMBIC_HEAD}')"))
    factory = make_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_single_page_en(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, num_pages=1, lang_guess="en", blocks_per_page=3)
    async with db_factory() as session:
        stats = await ingest_extract_dir(extract_dir, session, src=None)
        await session.commit()

    assert stats.pages == 1
    assert stats.blocks == 3
    assert isinstance(stats.document_id, int)


@pytest.mark.asyncio
async def test_ingest_multipage_ko(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, num_pages=3, lang_guess="ko", blocks_per_page=2)
    async with db_factory() as session:
        stats = await ingest_extract_dir(extract_dir, session, src=None, tgt="en")
        await session.commit()

    assert stats.pages == 3
    assert stats.blocks == 6


@pytest.mark.asyncio
async def test_ingest_persists_rows(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, num_pages=2, lang_guess="en", blocks_per_page=1)
    async with db_factory() as session:
        await ingest_extract_dir(extract_dir, session, src=None)
        await session.commit()

    async with db_factory() as session:
        docs = (await session.execute(text("SELECT COUNT(*) FROM documents"))).scalar()
        pages = (await session.execute(text("SELECT COUNT(*) FROM pages"))).scalar()
        blocks = (await session.execute(text("SELECT COUNT(*) FROM blocks"))).scalar()

    assert docs == 1
    assert pages == 2
    assert blocks == 2


@pytest.mark.asyncio
async def test_ingest_src_lang_explicit_overrides_lang_guess(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, lang_guess="mixed")
    async with db_factory() as session:
        await ingest_extract_dir(extract_dir, session, src="en")
        await session.commit()

    async with db_factory() as session:
        row = (await session.execute(text("SELECT src_lang FROM documents"))).first()
    assert row is not None and row[0] == "en"


@pytest.mark.asyncio
async def test_ingest_returns_correct_stats_document_id(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, num_pages=1, blocks_per_page=5)
    async with db_factory() as session:
        stats = await ingest_extract_dir(extract_dir, session, src="en")
        await session.commit()

    assert stats.pages == 1
    assert stats.blocks == 5
    assert stats.document_id >= 1


# ---------------------------------------------------------------------------
# Overwrite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overwrite_replaces_existing_document(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, num_pages=1, blocks_per_page=1)

    async with db_factory() as session:
        await ingest_extract_dir(extract_dir, session, src="en")
        await session.commit()

    async with db_factory() as session:
        await ingest_extract_dir(extract_dir, session, src="en", overwrite=True)
        await session.commit()

    async with db_factory() as session:
        count = (await session.execute(text("SELECT COUNT(*) FROM documents"))).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_overwrite_false_raises_on_duplicate(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, num_pages=1)

    async with db_factory() as session:
        await ingest_extract_dir(extract_dir, session, src="en")
        await session.commit()

    with pytest.raises(DocumentAlreadyIngested):
        async with db_factory() as session:
            await ingest_extract_dir(extract_dir, session, src="en", overwrite=False)


@pytest.mark.asyncio
async def test_overwrite_with_seeded_downstream_rows(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Overwrite must cascade through translations/threads/messages without FK error."""
    from datetime import UTC, datetime

    extract_dir = _make_extract_dir(tmp_path, num_pages=1, blocks_per_page=1)

    async with db_factory() as session:
        await ingest_extract_dir(extract_dir, session, src="en")
        await session.commit()

    # Seed downstream rows for the block just created.
    async with db_factory() as session:
        block = (await session.execute(text("SELECT id FROM blocks LIMIT 1"))).scalar_one()
        session.add(
            Translation(
                block_id=block,
                translated_text="translated",
                model="mock",
                status="done",
                updated_at=datetime.now(UTC),
            )
        )
        thread = Thread(block_id=block, title="t", created_at=datetime.now(UTC))
        session.add(thread)
        await session.flush()
        session.add(
            Message(
                thread_id=thread.id,
                role="user",
                content="hi",
                model=None,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    # Overwrite must not raise IntegrityError despite downstream rows existing.
    async with db_factory() as session:
        await ingest_extract_dir(extract_dir, session, src="en", overwrite=True)
        await session.commit()

    async with db_factory() as session:
        doc_count = (await session.execute(text("SELECT COUNT(*) FROM documents"))).scalar()
        trans_count = (await session.execute(text("SELECT COUNT(*) FROM translations"))).scalar()
        msg_count = (await session.execute(text("SELECT COUNT(*) FROM messages"))).scalar()
    assert doc_count == 1
    assert trans_count == 0
    assert msg_count == 0


# ---------------------------------------------------------------------------
# Language resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_raises_for_mixed_lang_without_src(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, lang_guess="mixed")
    with pytest.raises(IngestError, match="ambiguous"):
        async with db_factory() as session:
            await ingest_extract_dir(extract_dir, session, src=None)


@pytest.mark.asyncio
async def test_ingest_raises_for_unknown_lang_without_src(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, lang_guess="unknown")
    with pytest.raises(IngestError, match="ambiguous"):
        async with db_factory() as session:
            await ingest_extract_dir(extract_dir, session, src=None)


# ---------------------------------------------------------------------------
# Schema version gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_version_mismatch_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "bad_version.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        await conn.execute(text("INSERT INTO alembic_version VALUES ('9999')"))
    factory = make_session_factory(engine)

    extract_dir = _make_extract_dir(tmp_path, lang_guess="en")
    try:
        with pytest.raises(SchemaVersionMismatch):
            async with factory() as session:
                await ingest_extract_dir(extract_dir, session, src="en")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_schema_version_missing_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "no_alembic.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)

    extract_dir = _make_extract_dir(tmp_path, lang_guess="en")
    try:
        with pytest.raises(SchemaVersionMismatch):
            async with factory() as session:
                await ingest_extract_dir(extract_dir, session, src="en")
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Filesystem validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_doc_meta_raises(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path)
    (extract_dir / "doc_meta.json").unlink()
    with pytest.raises(IngestError, match=r"doc_meta\.json"):
        async with db_factory() as session:
            await ingest_extract_dir(extract_dir, session, src="en")


@pytest.mark.asyncio
async def test_missing_png_raises(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    extract_dir = _make_extract_dir(tmp_path, num_pages=1, write_pngs=False)
    (extract_dir / "pages").mkdir(exist_ok=True)
    (extract_dir / "pages" / "page_0001.json")  # JSON exists
    with pytest.raises(IngestError):
        async with db_factory() as session:
            await ingest_extract_dir(extract_dir, session, src="en")


@pytest.mark.asyncio
async def test_page_count_mismatch_raises(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    # declare 2 pages in doc_meta but only write 1 page file
    extract_dir = _make_extract_dir(tmp_path, num_pages=1, declare_num_pages=2)
    with pytest.raises(IngestError, match="mismatch"):
        async with db_factory() as session:
            await ingest_extract_dir(extract_dir, session, src="en")


@pytest.mark.asyncio
async def test_nonexistent_extract_dir_raises(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(IngestError, match="not found"):
        async with db_factory() as session:
            await ingest_extract_dir(missing, session, src="en")


@pytest.mark.asyncio
async def test_page_num_mismatch_between_filename_and_json_raises(
    tmp_path: Path, db_factory: async_sessionmaker[AsyncSession]
) -> None:
    """page_0001.json containing page_num=2 must be rejected."""
    extract_dir = _make_extract_dir(tmp_path, num_pages=1)
    page_json = extract_dir / "pages" / "page_0001.json"
    data = json.loads(page_json.read_text())
    data["page_num"] = 2  # corrupt: filename says 1, JSON says 2
    page_json.write_text(json.dumps(data))

    with pytest.raises(IngestError, match="page_num mismatch"):
        async with db_factory() as session:
            await ingest_extract_dir(extract_dir, session, src="en")
