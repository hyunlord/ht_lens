"""Phase 6d — translate_document on_progress callback."""

from __future__ import annotations

from pathlib import Path

import pytest

from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.pipeline import translate_document

from ._api_helpers import seed_minimal_document


@pytest.mark.asyncio
async def test_translate_callback_fires_every_10_and_on_last(
    api_db_path: Path, tmp_path: Path
) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session,
            tmp_dir=tmp_path,
            blocks_per_page=23,  # 23 text blocks → expect ticks at 10, 20, 23
            with_translations=False,
        )

        calls: list[tuple[int, int]] = []

        async def _on_progress(done: int, total: int) -> None:
            calls.append((done, total))

        await translate_document(seeded.doc_id, session, MockLLMClient(), on_progress=_on_progress)

    await engine.dispose()

    # Expect: 10/23, 20/23, 23/23 — strictly monotonic, total fixed.
    assert calls == [(10, 23), (20, 23), (23, 23)]


@pytest.mark.asyncio
async def test_translate_callback_under_concurrency_4(api_db_path: Path, tmp_path: Path) -> None:
    """Phase 7a-2: progress callback contract preserved under parallel
    execution (asyncio.as_completed counts in completion order)."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session,
            tmp_dir=tmp_path,
            blocks_per_page=23,
            with_translations=False,
        )

        calls: list[tuple[int, int]] = []

        async def _on_progress(done: int, total: int) -> None:
            calls.append((done, total))

        await translate_document(
            seeded.doc_id,
            session,
            MockLLMClient(),
            on_progress=_on_progress,
            concurrency=4,
        )

    await engine.dispose()
    # Identical contract under concurrency: ticks at 10, 20, 23, monotonic done.
    assert calls == [(10, 23), (20, 23), (23, 23)]


@pytest.mark.asyncio
async def test_translate_without_callback_is_backward_compat(
    api_db_path: Path, tmp_path: Path
) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session,
            tmp_dir=tmp_path,
            blocks_per_page=5,
            with_translations=False,
        )
        stats = await translate_document(seeded.doc_id, session, MockLLMClient())
    await engine.dispose()
    # Sanity: pipeline still produced translations.
    assert stats.translated + stats.cached > 0
