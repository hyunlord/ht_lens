"""Phase 7a-2 — concurrency unit tests for translate_document.

Verifies the Sub-goal A fix (sequential outer loop → asyncio.as_completed
+ Semaphore) actually parallelizes LLM calls and preserves dedup +
partial-failure semantics under concurrency.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.llm.errors import LLMPermanentError
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.pipeline import translate_document


@pytest_asyncio.fixture
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "translate_concurrency.db"
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
    blocks: list[tuple[str, str]],
) -> int:
    doc = Document(
        filename="t.pdf",
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
        bg_image_path="/tmp/page.png",
        rotation=0,
        render_dpi=200,
        pixel_width=1654,
        pixel_height=2339,
    )
    session.add(page)
    await session.flush()
    for i, (btype, btext) in enumerate(blocks):
        session.add(
            Block(
                page_id=page.id,
                block_local_id=f"b{i:03d}",
                type=btype,
                bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                order_idx=i,
                original_text=btext,
            )
        )
    await session.commit()
    return int(doc.id)


class _SleepyLLM(MockLLMClient):
    """MockLLMClient that awaits ``sleep_s`` before returning the translation."""

    model_name = "sleepy"

    def __init__(self, sleep_s: float) -> None:
        self.sleep_s = sleep_s
        self.call_count = 0

    async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
        self.call_count += 1
        await asyncio.sleep(self.sleep_s)
        return await super().translate(text, src, tgt, context=None)


@pytest.mark.asyncio
async def test_translate_concurrency_runs_in_parallel(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """5 distinct blocks x concurrency=5 with 0.1s LLM sleep should finish in
    well under 5 x 0.1s = 0.5s (sequential) — proving real parallelism."""
    llm = _SleepyLLM(sleep_s=0.1)
    async with db_factory() as session:
        doc_id = await _seed_doc(
            session,
            blocks=[("text", f"Distinct text {i}") for i in range(5)],
        )

    async with db_factory() as session:
        start = time.monotonic()
        stats = await translate_document(doc_id, session, llm, concurrency=5)
        elapsed = time.monotonic() - start

    assert stats.translated == 5
    assert stats.failed == 0
    assert llm.call_count == 5
    # Parallel ceiling: 0.1s + overhead. Allow generous 0.35s for DB + scheduling.
    assert elapsed < 0.35, f"expected parallel execution, got {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_translate_concurrency_one_sequential(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """concurrency=1 with 4 sleepy blocks must take ≥ 4 x sleep_s."""
    llm = _SleepyLLM(sleep_s=0.1)
    async with db_factory() as session:
        doc_id = await _seed_doc(
            session,
            blocks=[("text", f"Seq text {i}") for i in range(4)],
        )

    async with db_factory() as session:
        start = time.monotonic()
        stats = await translate_document(doc_id, session, llm, concurrency=1)
        elapsed = time.monotonic() - start

    assert stats.translated == 4
    assert llm.call_count == 4
    # Sequential lower bound: 4 x 0.1s = 0.4s. Allow some slack but enforce
    # the floor so this test would fail if concurrency=1 accidentally
    # parallelized (regression net).
    assert elapsed >= 0.38, f"expected sequential execution, got {elapsed:.3f}s"


class _FailingLLM(MockLLMClient):
    """MockLLM that raises LLMPermanentError for a specific input text."""

    model_name = "failing"

    def __init__(self, fail_text: str) -> None:
        self.fail_text = fail_text
        self.call_count = 0

    async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
        self.call_count += 1
        if text == self.fail_text:
            raise LLMPermanentError("intentional failure")
        return await super().translate(text, src, tgt, context=None)


@pytest.mark.asyncio
async def test_translate_partial_failure_does_not_block_others(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A single block's LLMPermanentError must not abort the other 4 blocks."""
    llm = _FailingLLM(fail_text="BAD BLOCK")
    async with db_factory() as session:
        doc_id = await _seed_doc(
            session,
            blocks=[
                ("text", "ok 1"),
                ("text", "ok 2"),
                ("text", "BAD BLOCK"),
                ("text", "ok 3"),
                ("text", "ok 4"),
            ],
        )

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm, concurrency=3)

    assert stats.failed == 1
    assert stats.translated == 4
    assert stats.cached == 0
    assert stats.skipped == 0


@pytest.mark.asyncio
async def test_translate_no_waiter_failure_does_not_leak_future_exception(
    db_factory: async_sessionmaker[AsyncSession],
    recwarn,
) -> None:
    """When a unique-text block fails (no duplicate waiter), the pending_futures
    future's exception must be consumed so asyncio doesn't log the classic
    "Future exception was never retrieved" warning.

    Regression net for Codex verify-cross §4: owner task did set_exception()
    without ever consuming the future when no duplicate waiter existed.
    """
    import warnings

    llm = _FailingLLM(fail_text="UNIQUE BAD")
    async with db_factory() as session:
        doc_id = await _seed_doc(
            session,
            blocks=[
                ("text", "ok 1"),
                ("text", "UNIQUE BAD"),  # only one occurrence — no waiter
                ("text", "ok 2"),
            ],
        )

    async with db_factory() as session:
        # Capture asyncio's "Future exception was never retrieved" log line.
        # In CPython this surfaces via the event loop's exception handler
        # only when the future is garbage-collected, so we explicitly
        # collect after the run.
        import gc

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            stats = await translate_document(doc_id, session, llm, concurrency=3)
            gc.collect()

    assert stats.failed == 1
    assert stats.translated == 2
    # Filter to messages that indicate an unretrieved future exception.
    leaked = [
        w
        for w in caught
        if "Future exception was never retrieved" in str(w.message)
        or "Task exception was never retrieved" in str(w.message)
    ]
    assert leaked == [], f"future exception leaked: {[str(w.message) for w in leaked]}"


class _CountingLLM(MockLLMClient):
    """MockLLM that counts unique translate() invocations."""

    model_name = "counting"

    def __init__(self) -> None:
        self.call_count = 0

    async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
        self.call_count += 1
        # Small sleep so two same-text tasks have a chance to interleave.
        await asyncio.sleep(0.02)
        return await super().translate(text, src, tgt, context=None)


class _RetryThenSucceedLLM(MockLLMClient):
    """Raises LLMTransientError on the first call for ``flaky_text``, succeeds after.

    Used to verify that the retry backoff sleep happens OUTSIDE the
    semaphore — otherwise a single flaky block would hold a slot during
    its 1s backoff, starving other concurrent blocks.
    """

    model_name = "retry-flaky"

    def __init__(self, flaky_text: str) -> None:
        from ht_lens.llm.errors import LLMTransientError

        self._transient = LLMTransientError
        self.flaky_text = flaky_text
        self.flaky_attempts = 0
        self.normal_block_durations: list[tuple[str, float]] = []

    async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
        if text == self.flaky_text:
            self.flaky_attempts += 1
            if self.flaky_attempts == 1:
                # First call: transient failure. Pipeline retries after
                # asyncio.sleep(2**0=1s) backoff.
                raise self._transient("simulated transient failure")
            return await super().translate(text, src, tgt, context=None)
        # Non-flaky blocks: short work.
        await asyncio.sleep(0.02)
        return await super().translate(text, src, tgt, context=None)


@pytest.mark.asyncio
async def test_translate_retry_backoff_does_not_block_other_blocks(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Phase 7a-2 / verify-cross R1: when one block enters retry backoff
    (~1s asyncio.sleep), the semaphore slot must be released so concurrent
    blocks keep flowing. With ``concurrency=2`` and 1 flaky + 2 normal
    blocks, the run must finish well under 1 + 2*0.02 = ~1.04s if the
    slot is freed during backoff; if the slot were held, the second
    normal block would queue behind the flaky one and total time would
    grow.
    """
    llm = _RetryThenSucceedLLM(flaky_text="FLAKY")
    async with db_factory() as session:
        doc_id = await _seed_doc(
            session,
            blocks=[
                ("text", "FLAKY"),
                ("text", "normal a"),
                ("text", "normal b"),
            ],
        )

    async with db_factory() as session:
        start = time.monotonic()
        stats = await translate_document(doc_id, session, llm, concurrency=2)
        elapsed = time.monotonic() - start

    assert stats.translated == 3
    assert stats.failed == 0
    assert llm.flaky_attempts == 2  # 1 transient + 1 success
    # Backoff is 2**0=1s. If the slot were held during backoff,
    # the two normal blocks would serialize behind the flaky one and
    # elapsed would be >= 1.04s; with slot release the normal blocks
    # finish during the backoff window, so total ≈ 1s + ε.
    # Use a tight upper bound: must finish under 1.2s to prove
    # the slot was actually released. (Hard floor is 1.0s — backoff.)
    assert 1.0 <= elapsed < 1.2, (
        f"retry slot-release contract violated: elapsed={elapsed:.3f}s. "
        "Expected ~1.0s (backoff) + parallel normals."
    )


@pytest.mark.asyncio
async def test_translate_deduplicates_duplicate_blocks_with_concurrency_2(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two blocks with identical text under concurrency=2 must produce a
    single LLM call (pending_futures dedup). Regression net for Codex
    debate §3.1: sequential pending_cache fails this under parallelism.
    """
    llm = _CountingLLM()
    async with db_factory() as session:
        doc_id = await _seed_doc(
            session,
            blocks=[
                ("text", "same text"),
                ("text", "same text"),
            ],
        )

    async with db_factory() as session:
        stats = await translate_document(doc_id, session, llm, concurrency=2)

    assert llm.call_count == 1, "expected pending_futures dedup → single LLM call"
    assert stats.translated == 1
    assert stats.cached == 1
    assert stats.failed == 0
