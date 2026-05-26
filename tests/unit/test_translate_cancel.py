"""Phase 7a-2 — cancellation policy for translate_document.

Spec (challenge §3.2): when ``translate_document`` is cancelled mid-run,
``Document.status`` is NOT updated (caller can resume), and any blocks
that completed before the cancel keep their committed ``status='translated'``
rows.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.db.session import ALEMBIC_HEAD, make_engine, make_session_factory
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.pipeline import translate_document


@pytest_asyncio.fixture
async def db_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "translate_cancel.db"
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


async def _seed_doc(session: AsyncSession, blocks: list[str]) -> int:
    doc = Document(
        filename="cancel.pdf",
        src_lang="en",
        tgt_lang="ko",
        status="ready_for_translation",
        created_at=datetime.now(UTC),
        src_pdf_sha256="c" * 64,
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
    for i, btext in enumerate(blocks):
        session.add(
            Block(
                page_id=page.id,
                block_local_id=f"b{i:03d}",
                type="text",
                bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                order_idx=i,
                original_text=btext,
            )
        )
    await session.commit()
    return int(doc.id)


class _SlowLLM(MockLLMClient):
    """First few blocks return fast; later blocks block forever (until cancelled)."""

    model_name = "slow"

    def __init__(self, fast_prefix: str, slow_prefix: str) -> None:
        self.fast_prefix = fast_prefix
        self.slow_prefix = slow_prefix
        self.fast_completed = asyncio.Event()
        self.fast_done_count = 0

    async def translate(self, text: str, src: str, tgt: str, *, context: object = None) -> str:
        if text.startswith(self.fast_prefix):
            await asyncio.sleep(0.01)
            self.fast_done_count += 1
            if self.fast_done_count == 2:
                self.fast_completed.set()
            return await MockLLMClient().translate(text, src, tgt, context=None)
        # Slow path: block until cancelled.
        await asyncio.sleep(60)
        return "should never return"


@pytest.mark.asyncio
async def test_translate_cancel_mid_run_preserves_state(
    db_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Cancel translate_document after 2/4 blocks complete; verify:
    - Document.status NOT changed from pre-run value
    - The 2 fast blocks have committed Translation rows with status='translated'
    - The 2 slow blocks have no Translation row (LLM call never completed)
    """
    llm = _SlowLLM(fast_prefix="FAST", slow_prefix="SLOW")
    async with db_factory() as session:
        doc_id = await _seed_doc(
            session,
            blocks=["FAST 1", "FAST 2", "SLOW 1", "SLOW 2"],
        )
        await session.refresh(await session.get(Document, doc_id))
        pre_status = (await session.get(Document, doc_id)).status
    assert pre_status == "ready_for_translation"

    async with db_factory() as session:
        task = asyncio.create_task(translate_document(doc_id, session, llm, concurrency=4))
        # Wait until the 2 fast blocks have finished, then cancel.
        await asyncio.wait_for(llm.fast_completed.wait(), timeout=5.0)
        # Give the pipeline a tick to record progress + commit.
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # Verify post-cancel state in a fresh session.
    async with db_factory() as session:
        doc_after = await session.get(Document, doc_id)
        assert doc_after is not None
        assert doc_after.status == "ready_for_translation", (
            f"Document.status changed after cancel: {doc_after.status!r}"
        )
        fast_blocks = (
            (await session.execute(select(Block).where(Block.original_text.like("FAST%"))))
            .scalars()
            .all()
        )
        rows = (
            (
                await session.execute(
                    select(Translation).where(Translation.block_id.in_([b.id for b in fast_blocks]))
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2, f"expected 2 committed translations for FAST blocks, got {len(rows)}"
        assert all(r.status == "translated" for r in rows)

        slow_blocks = (
            (await session.execute(select(Block).where(Block.original_text.like("SLOW%"))))
            .scalars()
            .all()
        )
        slow_rows = (
            (
                await session.execute(
                    select(Translation).where(Translation.block_id.in_([b.id for b in slow_blocks]))
                )
            )
            .scalars()
            .all()
        )
        assert slow_rows == [], "SLOW blocks must not have committed translations"
