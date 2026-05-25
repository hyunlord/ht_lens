"""Unit tests for the brute-force vector searcher — Phase 7a."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.search import SearchHit, search
from ht_lens.embedding.service import MockEmbeddingClient, text_source_hash
from ht_lens.embedding.store import upsert_embedding

# ---------------------------------------------------------------------------
# Fixture: corpus across two docs with deterministic mock vectors
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def corpus_factory(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    db_path = tmp_path / "search_test.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)

    client = MockEmbeddingClient(dim=32)
    async with factory() as session:
        for doc_id in (1, 2):
            doc = Document(
                id=doc_id,
                filename=f"doc{doc_id}.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
                src_pdf_sha256=f"{doc_id:064x}",
            )
            session.add(doc)
            await session.flush()
            page = Page(
                doc_id=doc_id,
                page_num=1,
                width=500.0,
                height=700.0,
                bg_image_path=f"/tmp/{doc_id}.png",
                rotation=0,
                render_dpi=200,
                pixel_width=1000,
                pixel_height=1400,
            )
            session.add(page)
            await session.flush()
            # 5 long blocks per doc + 1 short fragment per doc
            for i in range(5):
                text = f"Doc {doc_id} para {i} long enough to pass minimum char filter."
                blk = Block(
                    page_id=page.id,
                    block_local_id=f"d{doc_id}_b{i:03d}",
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
            # Short fragment block (must be filtered by min_chars).
            short_text = "hi"
            short_blk = Block(
                page_id=page.id,
                block_local_id=f"d{doc_id}_short",
                type="text",
                bbox_json=json.dumps([0.0, 200.0, 50.0, 215.0]),
                order_idx=99,
                original_text=short_text,
            )
            session.add(short_blk)
            await session.flush()
            short_vec = client.encode([short_text])[0]
            await upsert_embedding(
                session,
                block_id=short_blk.id,
                vector=short_vec,
                model=client.model_name,
                dim=client.dim,
                source_hash=text_source_hash(short_text),
            )
        await session.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_search_returns_top_k(corpus_factory) -> None:
    """Top-K limit is honored (and we get the most-similar block first)."""
    client = MockEmbeddingClient(dim=32)
    async with corpus_factory() as session:
        # Use the actual text from doc 2 / block 0 as the query — it
        # is in the corpus, so it must score 1.0 and come first.
        query_text = "Doc 2 para 0 long enough to pass minimum char filter."
        q = client.encode([query_text])[0]
        hits = await search(session, query_vector=q, top_k=3, threshold=0.0, min_chars=10)
    assert len(hits) == 3
    # The exact-match block (doc 2 long 0) must be first with score ~1.0.
    assert hits[0].doc_id == 2
    assert hits[0].score > 0.99


@pytest.mark.asyncio
async def test_search_threshold_drops_low_scores(corpus_factory) -> None:
    """Threshold filter excludes weakly-matching candidates."""
    client = MockEmbeddingClient(dim=32)
    async with corpus_factory() as session:
        query_text = "Doc 1 para 2 long enough to pass minimum char filter."
        q = client.encode([query_text])[0]
        # Only the exact-match block (score 1.0) is above 0.95.
        hits = await search(session, query_vector=q, top_k=10, threshold=0.95, min_chars=10)
    assert all(h.score >= 0.95 for h in hits)
    assert len(hits) == 1  # the exact match


@pytest.mark.asyncio
async def test_search_excludes_same_doc(corpus_factory) -> None:
    """exclude_doc_ids guarantees cross-doc-only semantics."""
    client = MockEmbeddingClient(dim=32)
    async with corpus_factory() as session:
        query_text = "Doc 1 para 0 long enough to pass minimum char filter."
        q = client.encode([query_text])[0]
        hits = await search(
            session,
            query_vector=q,
            top_k=10,
            threshold=0.0,
            exclude_doc_ids={1},
            min_chars=10,
        )
    assert hits, "should still find doc 2 blocks"
    assert all(h.doc_id != 1 for h in hits), f"same-doc leak: {hits}"


@pytest.mark.asyncio
async def test_search_min_chars_filters_short_fragments(corpus_factory) -> None:
    """Codex debate §3: short fragments must not flood top-K."""
    client = MockEmbeddingClient(dim=32)
    async with corpus_factory() as session:
        # The short blocks ("hi") would otherwise rank somewhere; with
        # min_chars=50 they are excluded from the result set.
        q = client.encode(["hi"])[0]
        hits = await search(session, query_vector=q, top_k=20, threshold=0.0, min_chars=50)
    block_ids = {h.block_id for h in hits}
    # Pull short-block ids back from the DB by their distinctive text.
    from sqlalchemy import select

    from ht_lens.db.models import Block

    async with corpus_factory() as session:
        short_ids = {
            b.id
            for b in (await session.execute(select(Block).where(Block.original_text == "hi")))
            .scalars()
            .all()
        }
    assert short_ids and not (short_ids & block_ids), (
        f"short fragments leaked into top-K: short={short_ids} hits={block_ids}"
    )


@pytest.mark.asyncio
async def test_search_empty_corpus_returns_empty(tmp_path: Path) -> None:
    """No embeddings stored → empty result, no crash."""
    db_path = tmp_path / "empty.db"
    engine = make_engine(db_path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = make_session_factory(engine)
    async with factory() as session:
        q = np.ones(32, dtype=np.float32) / np.sqrt(32)
        hits = await search(session, query_vector=q, top_k=5, threshold=0.0)
    await engine.dispose()
    assert hits == []


@pytest.mark.asyncio
async def test_search_rejects_dim_mismatch(corpus_factory) -> None:
    """Query vector dim must match stored embedding dim."""
    async with corpus_factory() as session:
        wrong_q = np.zeros(64, dtype=np.float32)
        wrong_q[0] = 1.0
        with pytest.raises(ValueError, match="does not match stored embeddings dim"):
            await search(session, query_vector=wrong_q, top_k=5)


@pytest.mark.asyncio
async def test_search_returns_hits_in_descending_score_order(corpus_factory) -> None:
    """Sanity: top-K is sorted high → low so the caller can rely on order."""
    client = MockEmbeddingClient(dim=32)
    async with corpus_factory() as session:
        query_text = "Doc 2 para 0 long enough to pass minimum char filter."
        q = client.encode([query_text])[0]
        hits = await search(session, query_vector=q, top_k=5, threshold=0.0, min_chars=10)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True), f"unsorted: {scores}"


@pytest.mark.asyncio
async def test_searchhit_is_immutable_dataclass() -> None:
    """SearchHit is frozen — protects against accidental mutation."""
    hit = SearchHit(block_id=1, doc_id=2, score=0.9)
    with pytest.raises((AttributeError, Exception), match=""):  # FrozenInstanceError
        hit.score = 0.5  # type: ignore[misc]
