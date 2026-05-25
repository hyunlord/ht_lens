"""Phase 7a R1 fix — Codex verify-cross §4 #4: ``load_all`` must not
desynchronize ``ids`` and ``matrix`` when the corpus contains rows of
mismatched dimension (e.g. after a future model swap leaves stragglers).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.search import search
from ht_lens.embedding.service import MockEmbeddingClient, text_source_hash
from ht_lens.embedding.store import load_all, upsert_embedding


@pytest_asyncio.fixture
async def two_dim_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "mixed_dim.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)

    # Seed 3 majority-dim rows + 1 outlier-dim row.
    async with factory() as session:
        doc = Document(
            id=1,
            filename="doc.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="translated",
            created_at=datetime.now(UTC),
            src_pdf_sha256="a" * 64,
        )
        session.add(doc)
        await session.flush()
        page = Page(
            doc_id=1,
            page_num=1,
            width=500.0,
            height=700.0,
            bg_image_path="/tmp/p.png",
            rotation=0,
            render_dpi=200,
            pixel_width=1000,
            pixel_height=1400,
        )
        session.add(page)
        await session.flush()
        majority = MockEmbeddingClient(dim=16, model_name="model-a")
        minority = MockEmbeddingClient(dim=32, model_name="model-b")
        for i, (client, text) in enumerate(
            [
                (majority, "Majority row one with enough text content to pass filters."),
                (majority, "Majority row two with enough text content to pass filters."),
                (majority, "Majority row three with enough text content to pass filters."),
                (minority, "Outlier row with different embedding dimension."),
            ]
        ):
            blk = Block(
                page_id=page.id,
                block_local_id=f"b{i:03d}",
                type="text",
                bbox_json=json.dumps([0.0, float(i * 20), 100.0, float(i * 20 + 15)]),
                order_idx=i,
                original_text=text,
            )
            session.add(blk)
            await session.flush()
            vec = client.encode([text])[0]
            await upsert_embedding(
                session,
                block_id=blk.id,
                vector=vec,
                model=client.model_name,
                dim=client.dim,
                source_hash=text_source_hash(text),
            )
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_load_all_drops_outliers_from_ids_and_matrix(two_dim_factory) -> None:
    """ids, matrix, models must all stay in lockstep."""
    async with two_dim_factory() as session:
        ids, matrix, models = await load_all(session)
    assert matrix.shape == (3, 16), f"unexpected matrix shape {matrix.shape}"
    assert len(ids) == 3, f"ids out of sync: {ids}"
    assert len(models) == 3
    # Outlier row must be excluded entirely.
    assert all(m == "model-a" for m in models)


@pytest.mark.asyncio
async def test_search_does_not_index_into_outlier(two_dim_factory) -> None:
    """Search must never return the outlier block_id (it's not in ids)."""
    majority = MockEmbeddingClient(dim=16, model_name="model-a")
    async with two_dim_factory() as session:
        q = majority.encode(["Majority row one with enough text content to pass filters."])[0]
        hits = await search(session, query_vector=q, top_k=5, threshold=0.0, min_chars=10)
    block_ids = {h.block_id for h in hits}
    # Outlier was block 4 (0-indexed); majority blocks are 1-3.
    assert 4 not in block_ids, f"outlier leaked into search: {hits}"
