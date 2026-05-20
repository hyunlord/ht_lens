"""Phase 3 — block context builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from ht_lens.api.chat_context import BlockNotFoundError, build_block_context
from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import seed_minimal_document


@pytest.mark.asyncio
async def test_build_block_context_window_center(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "ctx.db")
    factory = make_session_factory(engine)
    from ht_lens.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=5)
        # block_ids: [b1..b5] order_idx 0..4. center=3rd block (idx=2)
        center_id = seeded.block_ids[2]
        text = await build_block_context(session, center_id, radius=2)

    await engine.dispose()

    assert "[Page 1, Block p1_b003]" in text
    assert "원문:" in text
    assert "번역:" in text
    assert "주변 맥락 (±2 blocks):" in text
    # window covers b1..b5 (5 blocks)
    for tag in ["p1_b001", "p1_b002", "p1_b003", "p1_b004", "p1_b005"]:
        assert tag in text
    assert text.count("→") == 1  # only center marked


@pytest.mark.asyncio
async def test_build_block_context_first_block_truncates_left(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "ctx.db")
    factory = make_session_factory(engine)
    from ht_lens.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=5)
        first_id = seeded.block_ids[0]
        text = await build_block_context(session, first_id, radius=2)
    await engine.dispose()

    # window: [b1, b2, b3] (no b-1, b-2)
    assert "p1_b001" in text and "p1_b002" in text and "p1_b003" in text
    assert "p1_b004" not in text


@pytest.mark.asyncio
async def test_build_block_context_last_block_truncates_right(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "ctx.db")
    factory = make_session_factory(engine)
    from ht_lens.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=5)
        last_id = seeded.block_ids[-1]
        text = await build_block_context(session, last_id, radius=2)
    await engine.dispose()

    assert "p1_b003" in text and "p1_b004" in text and "p1_b005" in text
    assert "p1_b002" not in text


@pytest.mark.asyncio
async def test_build_block_context_radius_zero_omits_window(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "ctx.db")
    factory = make_session_factory(engine)
    from ht_lens.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=3)
        text = await build_block_context(session, seeded.block_ids[1], radius=0)
    await engine.dispose()

    assert "주변 맥락" not in text


@pytest.mark.asyncio
async def test_build_block_context_missing_translation_fallback(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "ctx.db")
    factory = make_session_factory(engine)
    from ht_lens.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session, tmp_dir=tmp_path, blocks_per_page=2, with_translations=False
        )
        text = await build_block_context(session, seeded.block_ids[0], radius=1)
    await engine.dispose()

    assert "번역: (번역 없음)" in text


@pytest.mark.asyncio
async def test_build_block_context_image_block_label(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "ctx.db")
    factory = make_session_factory(engine)
    from sqlalchemy import update

    from ht_lens.db.base import Base
    from ht_lens.db.models import Block

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session,
            tmp_dir=tmp_path,
            blocks_per_page=3,
            block_types=("text", "image", "text"),
        )
        # Force the image block's original_text to empty
        await session.execute(
            update(Block).where(Block.id == seeded.block_ids[1]).values(original_text="")
        )
        await session.commit()
        text = await build_block_context(session, seeded.block_ids[0], radius=2)
    await engine.dispose()

    assert "[빈 image 블록]" in text


@pytest.mark.asyncio
async def test_build_block_context_unknown_block_raises(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "ctx.db")
    factory = make_session_factory(engine)
    from ht_lens.db.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        with pytest.raises(BlockNotFoundError):
            await build_block_context(session, 99999, radius=2)
    await engine.dispose()
