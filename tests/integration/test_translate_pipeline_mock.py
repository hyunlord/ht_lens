"""Integration tests for translate_document using MockLLMClient."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.errors import SchemaVersionMismatch
from ht_lens.llm.errors import LLMPermanentError, LLMTransientError
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.pipeline import translate_document

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory with ORM schema + alembic_version = ALEMBIC_HEAD."""
    db_path = tmp_path / "translate_test.db"
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


async def _seed_doc(
    session: AsyncSession,
    *,
    src_lang: str = "en",
    tgt_lang: str = "ko",
    blocks: list[tuple[str, str]] | None = None,
) -> tuple[int, list[int]]:
    """Insert one document + one page + given blocks. Returns (doc_id, [block_ids])."""
    if blocks is None:
        blocks = [("text", "Hello world"), ("text", "Second block")]
    doc = Document(
        filename="test.pdf",
        src_lang=src_lang,
        tgt_lang=tgt_lang,
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
        bg_image_path="/tmp/page.png",
        rotation=0,
        render_dpi=200,
        pixel_width=1654,
        pixel_height=2339,
    )
    session.add(page)
    await session.flush()

    block_ids: list[int] = []
    for i, (btype, btext) in enumerate(blocks):
        b = Block(
            page_id=page.id,
            block_local_id=f"b{i:03d}",
            type=btype,
            bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
            order_idx=i,
            original_text=btext,
        )
        session.add(b)
        await session.flush()
        block_ids.append(b.id)

    await session.commit()
    return doc.id, block_ids


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_two_text_blocks(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, block_ids = await _seed_doc(session)

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm)

    assert stats.translated == 2
    assert stats.skipped == 0
    assert stats.failed == 0
    assert stats.cached == 0

    async with db_factory() as session:
        for bid in block_ids:
            tr = await session.get(Translation, bid)
            assert tr is not None
            assert tr.status == "translated"
            assert "[KO]" in tr.translated_text


@pytest.mark.asyncio
async def test_translate_skips_image_blocks(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, _ = await _seed_doc(
            session, blocks=[("image", ""), ("text", "Hello"), ("header", "Title")]
        )

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm)

    assert stats.translated == 2  # text + header
    assert stats.skipped == 1  # image


@pytest.mark.asyncio
async def test_translate_skips_already_translated(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, _ = await _seed_doc(session)

    # First run
    async with db_factory() as session:
        stats1 = await translate_document(doc_id, session, llm)
    assert stats1.translated == 2

    # Second run — should skip all
    async with db_factory() as session:
        stats2 = await translate_document(doc_id, session, llm)
    assert stats2.translated == 0
    assert stats2.skipped == 2
    assert stats2.cached == 0


@pytest.mark.asyncio
async def test_translate_deduplicates_duplicate_blocks_in_memory(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Same text twice in one doc → second block served from in-memory cache."""
    llm = MockLLMClient()
    call_count = 0
    original_translate = llm.translate

    async def counting_translate(text: str, src: str, tgt: str, *, context: object = None) -> str:
        nonlocal call_count
        call_count += 1
        return await original_translate(text, src, tgt, context=None)

    llm.translate = counting_translate  # type: ignore[method-assign]

    async with db_factory() as session:
        doc_id, _ = await _seed_doc(session, blocks=[("text", "same text"), ("text", "same text")])

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm)

    assert call_count == 1  # LLM called only once for duplicate text
    assert stats.translated == 1
    assert stats.cached == 1


@pytest.mark.asyncio
async def test_translate_db_cache_hit_on_second_doc(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Same text in a second doc is served from DB cache (cross-run)."""
    llm = MockLLMClient()
    call_count = 0
    original_translate = llm.translate

    async def counting_translate(text: str, src: str, tgt: str, *, context: object = None) -> str:
        nonlocal call_count
        call_count += 1
        return await original_translate(text, src, tgt, context=None)

    llm.translate = counting_translate  # type: ignore[method-assign]

    shared_text = "Shared paragraph."

    # First document
    async with db_factory() as session:
        doc_id1, _ = await _seed_doc(session, blocks=[("text", shared_text)])
    async with db_factory() as session:
        stats1 = await translate_document(doc_id1, session, llm)
    assert stats1.translated == 1
    calls_after_first = call_count

    # Second document with same text
    async with db_factory() as session:
        doc_id2, _ = await _seed_doc(session, blocks=[("text", shared_text)])
    async with db_factory() as session:
        stats2 = await translate_document(doc_id2, session, llm)
    assert stats2.cached == 1
    assert stats2.translated == 0
    assert call_count == calls_after_first  # no new LLM call


@pytest.mark.asyncio
async def test_translate_header_blocks_translated(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, block_ids = await _seed_doc(session, blocks=[("header", "Introduction")])

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm)

    assert stats.translated == 1
    async with db_factory() as session:
        tr = await session.get(Translation, block_ids[0])
        assert tr is not None and tr.status == "translated"


# ---------------------------------------------------------------------------
# Retry and failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_marks_failed_on_permanent_error(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    class FailLLM(MockLLMClient):
        async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
            raise LLMPermanentError("auth failure")

    async with db_factory() as session:
        doc_id, block_ids = await _seed_doc(session, blocks=[("text", "x")])

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, FailLLM(), max_retries=0)

    assert stats.failed == 1
    async with db_factory() as session:
        tr = await session.get(Translation, block_ids[0])
        assert tr is not None and tr.status == "failed"


@pytest.mark.asyncio
async def test_translate_retries_transient_then_succeeds(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    attempts: list[int] = []

    class FlakyLLM(MockLLMClient):
        async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
            attempts.append(1)
            if len(attempts) < 2:
                raise LLMTransientError("temporary")
            return f"[KO] {text}"

    async with db_factory() as session:
        doc_id, block_ids = await _seed_doc(session, blocks=[("text", "hello")])

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, FlakyLLM(), max_retries=2)

    assert stats.translated == 1
    assert len(attempts) == 2
    async with db_factory() as session:
        tr = await session.get(Translation, block_ids[0])
        assert tr is not None and tr.status == "translated"


@pytest.mark.asyncio
async def test_translate_retry_exhaustion_marks_failed(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    class AlwaysTransientLLM(MockLLMClient):
        async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
            raise LLMTransientError("always fails")

    async with db_factory() as session:
        doc_id, _ = await _seed_doc(session, blocks=[("text", "x")])

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, AlwaysTransientLLM(), max_retries=1)

    assert stats.failed == 1


@pytest.mark.asyncio
async def test_retry_failed_reprocesses_failed_blocks(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    class FailLLM(MockLLMClient):
        async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
            raise LLMPermanentError("fail")

    async with db_factory() as session:
        doc_id, block_ids = await _seed_doc(session, blocks=[("text", "x")])

    # First run — fail
    async with db_factory() as session:
        stats1 = await translate_document(doc_id, session, FailLLM(), max_retries=0)
    assert stats1.failed == 1

    # Second run without retry_failed — should skip the failed block
    async with db_factory() as session:
        stats2 = await translate_document(doc_id, session, FailLLM(), max_retries=0)
    assert stats2.skipped == 1
    assert stats2.failed == 0

    # Third run with retry_failed — should re-attempt (and fail again with FailLLM)
    async with db_factory() as session:
        stats3 = await translate_document(
            doc_id, session, MockLLMClient(), max_retries=0, retry_failed=True
        )
    assert stats3.translated == 1  # now succeeds with real mock
    async with db_factory() as session:
        tr = await session.get(Translation, block_ids[0])
        assert tr is not None and tr.status == "translated"


@pytest.mark.asyncio
async def test_retry_failed_skips_already_translated(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, _ = await _seed_doc(session)

    async with db_factory() as session:
        await translate_document(doc_id, session, llm)

    # retry_failed=True should NOT re-translate already-done blocks
    call_count = 0

    class CountingLLM(MockLLMClient):
        async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
            nonlocal call_count
            call_count += 1
            return f"[KO] {text}"

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, CountingLLM(), retry_failed=True)
    assert call_count == 0
    assert stats.skipped == 2


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_returns_stats_without_writing(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, block_ids = await _seed_doc(session)

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm, dry_run=True)

    # Estimated: 2 LLM calls (no prior translations)
    assert stats.translated == 2
    assert stats.cached == 0

    # No translations written
    async with db_factory() as session:
        for bid in block_ids:
            tr = await session.get(Translation, bid)
            assert tr is None


@pytest.mark.asyncio
async def test_dry_run_counts_cache_hits(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, _ = await _seed_doc(session)

    # Actual run first
    async with db_factory() as session:
        await translate_document(doc_id, session, llm)

    # Dry run on same doc — all blocks already translated → all are cache hits
    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm, dry_run=True)

    assert stats.cached == 2
    assert stats.translated == 0


@pytest.mark.asyncio
async def test_dry_run_deduplicates_duplicate_blocks(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Dry-run must not overcount estimated_llm_calls for duplicate texts."""
    llm = MockLLMClient()
    async with db_factory() as session:
        doc_id, _ = await _seed_doc(
            session, blocks=[("text", "same"), ("text", "same"), ("text", "different")]
        )

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm, dry_run=True)

    # "same" x 2 + "different" x 1 = 3 blocks; second "same" is deduped
    assert stats.translated == 2  # "same" once + "different"
    assert stats.cached == 1  # second "same" is in-run dedup


@pytest.mark.asyncio
async def test_translate_stats_failed_count(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """stats.failed counts blocks that end up with status='failed'."""

    class FailLLM(MockLLMClient):
        async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
            raise LLMPermanentError("always fail")

    async with db_factory() as session:
        doc_id, block_ids = await _seed_doc(session, blocks=[("text", "a"), ("text", "b")])

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, FailLLM(), max_retries=0)

    assert stats.failed == 2
    async with db_factory() as session:
        for bid in block_ids:
            tr = await session.get(Translation, bid)
            assert tr is not None and tr.status == "failed"


# ---------------------------------------------------------------------------
# Schema check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_raises_schema_mismatch_without_alembic(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "no_alembic.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            with pytest.raises(SchemaVersionMismatch):
                await translate_document(1, session, MockLLMClient())
    finally:
        await engine.dispose()
