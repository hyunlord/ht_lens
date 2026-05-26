"""Phase 7a — chat_context cross-doc RAG section tests (mock embedding)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.api.chat_context import (
    BlockNotFoundError,
    build_block_context,
    build_block_context_with_refs,
)
from ht_lens.db.base import Base
from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.service import MockEmbeddingClient, text_source_hash
from ht_lens.embedding.store import upsert_embedding


@pytest_asyncio.fixture
async def two_doc_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Two docs with one matching paragraph each so cross-doc search returns."""
    db_path = tmp_path / "rag_chat.db"
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
            # 3 blocks per doc. Block i has IDENTICAL text across docs so
            # cross-doc search produces an exact (score~1.0) match for the
            # corresponding block in the OTHER doc.
            for i in range(3):
                text = f"Shared paragraph index {i} long enough for vector search content."
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
                session.add(
                    Translation(
                        block_id=blk.id,
                        translated_text=f"[KO] {text}",
                        model="mock",
                        status="translated",
                        updated_at=datetime.now(UTC),
                    )
                )
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
async def test_cross_doc_disabled_returns_same_doc_only(two_doc_factory) -> None:
    """``enable_cross_doc=False`` reverts to Phase 3 behavior."""
    async with two_doc_factory() as session:
        text, refs = await build_block_context_with_refs(
            session,
            block_id=1,  # doc 1, block 0
            radius=2,
            embedding_client=MockEmbeddingClient(dim=32),
            enable_cross_doc=False,
        )
    assert refs == []
    assert "다른 문서 관련 참조" not in text


@pytest.mark.asyncio
async def test_cross_doc_no_client_skips_section(two_doc_factory) -> None:
    """``embedding_client=None`` also disables RAG (graceful fail-soft)."""
    async with two_doc_factory() as session:
        text, refs = await build_block_context_with_refs(
            session,
            block_id=1,
            radius=2,
            embedding_client=None,
            enable_cross_doc=True,
        )
    assert refs == []
    assert "다른 문서 관련 참조" not in text


@pytest.mark.asyncio
async def test_cross_doc_includes_other_doc_blocks(two_doc_factory) -> None:
    """Enabled + client present → top-K from the OTHER doc appears."""
    client = MockEmbeddingClient(dim=32)
    async with two_doc_factory() as session:
        text, refs = await build_block_context_with_refs(
            session,
            block_id=1,  # doc 1, block 0 → matches doc 2 / block 0
            radius=0,  # focus on RAG section only
            embedding_client=client,
            enable_cross_doc=True,
            cross_doc_top_k=3,
            cross_doc_threshold=0.0,
        )
    assert refs, "expected cross-doc hits"
    assert all(r.doc_id != 1 for r in refs), f"same-doc leak: {refs}"
    # The exact-text match in doc 2 should be the top hit (~1.0 score).
    top = max(refs, key=lambda r: r.score)
    assert top.doc_id == 2
    assert top.score > 0.99
    assert "다른 문서 관련 참조" in text
    assert top.doc_filename == "doc2.pdf"


@pytest.mark.asyncio
async def test_cross_doc_excludes_target_block(two_doc_factory) -> None:
    """The target block itself must never appear in its own related refs
    (covered by exclude_block_ids alongside exclude_doc_ids)."""
    client = MockEmbeddingClient(dim=32)
    async with two_doc_factory() as session:
        _, refs = await build_block_context_with_refs(
            session,
            block_id=1,
            radius=0,
            embedding_client=client,
            cross_doc_top_k=5,
            cross_doc_threshold=0.0,
        )
    assert all(r.block_id != 1 for r in refs)


@pytest.mark.asyncio
async def test_cross_doc_top_k_zero_skips_section(two_doc_factory) -> None:
    """top_k=0 → no RAG section, even when client+enable are present."""
    client = MockEmbeddingClient(dim=32)
    async with two_doc_factory() as session:
        text, refs = await build_block_context_with_refs(
            session,
            block_id=1,
            radius=0,
            embedding_client=client,
            enable_cross_doc=True,
            cross_doc_top_k=0,
        )
    assert refs == []
    assert "다른 문서 관련 참조" not in text


@pytest.mark.asyncio
async def test_block_not_found_still_raises(two_doc_factory) -> None:
    """Unknown block id continues to raise the documented error."""
    async with two_doc_factory() as session:
        with pytest.raises(BlockNotFoundError):
            await build_block_context(
                session,
                block_id=9999,
                embedding_client=MockEmbeddingClient(dim=32),
            )


class _CountingEmbeddingClient(MockEmbeddingClient):
    """Wraps MockEmbeddingClient to count encode() invocations."""

    def __init__(self, dim: int = 32) -> None:
        super().__init__(dim=dim)
        self.encode_call_count = 0

    def encode(self, texts):  # type: ignore[override]
        self.encode_call_count += len(texts)
        return super().encode(texts)


@pytest.mark.asyncio
async def test_cross_doc_reuses_stored_vector_when_fresh(two_doc_factory) -> None:
    """Phase 7a-2: when target block's embedding row exists and source_hash
    matches the current text, build_block_context_with_refs must NOT call
    encode()."""
    client = _CountingEmbeddingClient(dim=32)
    async with two_doc_factory() as session:
        _, refs = await build_block_context_with_refs(
            session,
            block_id=1,
            radius=0,
            embedding_client=client,
            cross_doc_top_k=3,
            cross_doc_threshold=0.0,
        )
    assert refs, "cross-doc search should still produce results"
    assert client.encode_call_count == 0, (
        f"expected stored vector reuse, got {client.encode_call_count} encode call(s)"
    )
