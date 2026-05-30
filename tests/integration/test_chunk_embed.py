"""Phase 8b — chunk embedding backfill integration tests."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from ht_lens.db.models import (
    Block,
    BlockEmbedding,
    Chunk,
    ChunkEmbedding,
    ChunkTranslation,
    Document,
    Page,
)
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.chunk_backfill import backfill_chunks


class _MockEmbed:
    model_name = "mock-embed"
    dim = 8

    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        self.calls += 1
        v = np.ones((len(texts), self.dim), dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


async def _factory(db_path):  # type: ignore[no-untyped-def]
    engine = make_engine(db_path)
    return engine, make_session_factory(engine)


async def _seed_translated_chunks(factory) -> int:  # type: ignore[no-untyped-def]
    async with factory() as s:
        doc = Document(
            filename="m.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="translated",
            created_at=datetime.now(UTC),
            extractor="mineru",
        )
        s.add(doc)
        await s.flush()
        specs = [
            ("heading", "Section 28.4 about latent factor models and priors"),
            ("text", "A sufficiently long body paragraph well over thirty chars."),
            ("text", "short"),  # < 30 chars → skipped
            ("equation", "$$E=mc^2$$"),  # not text/heading → skipped
            ("image", "a caption-bearing image"),
        ]
        for i, (typ, content) in enumerate(specs):
            ch = Chunk(
                doc_id=doc.id,
                page_idx=0,
                order_idx=i,
                type=typ,
                bbox_json="[0,0,1,1]",
                content=content,
            )
            s.add(ch)
            await s.flush()
            s.add(
                ChunkTranslation(
                    chunk_id=ch.id,
                    translated_text="[KO] x",
                    model="mock",
                    status="translated",
                    updated_at=datetime.now(UTC),
                )
            )
        await s.commit()
        return doc.id


@pytest.mark.asyncio
async def test_backfill_embeds_only_text_heading_over_min(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _seed_translated_chunks(factory)
        async with factory() as s:
            stats = await backfill_chunks(s, _MockEmbed(), doc_id=doc_id)
        # heading + 1 long text = 2 (short text, equation, image excluded)
        assert stats["candidates"] == 2
        assert stats["embedded"] == 2
        async with factory() as s:
            from sqlalchemy import func, select

            n = (await s.execute(select(func.count()).select_from(ChunkEmbedding))).scalar()
        assert n == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_idempotent(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _seed_translated_chunks(factory)
        async with factory() as s:
            await backfill_chunks(s, _MockEmbed(), doc_id=doc_id)
        async with factory() as s:
            stats2 = await backfill_chunks(s, _MockEmbed(), doc_id=doc_id)
        assert stats2["embedded"] == 0 and stats2["skipped"] == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_model_change_refreshes(api_db_path) -> None:  # type: ignore[no-untyped-def]
    class OtherModel(_MockEmbed):
        model_name = "other-embed"

    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _seed_translated_chunks(factory)
        async with factory() as s:
            await backfill_chunks(s, _MockEmbed(), doc_id=doc_id)
        async with factory() as s:
            stats2 = await backfill_chunks(s, OtherModel(), doc_id=doc_id)
        # model bump → re-embed, not skip (matches Phase 7a regression fix)
        assert stats2["embedded"] == 2 and stats2["skipped"] == 0
        async with factory() as s:
            from sqlalchemy import select

            models = {e.model for e in (await s.execute(select(ChunkEmbedding))).scalars()}
        assert models == {"other-embed"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_1x_block_embeddings_untouched(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        # Seed a 1.x block_embedding row.
        async with factory() as s:
            doc = Document(
                filename="legacy.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
            )
            s.add(doc)
            await s.flush()
            pg = Page(
                doc_id=doc.id,
                page_num=1,
                width=1.0,
                height=1.0,
                bg_image_path="/x.png",
                pixel_width=1,
                pixel_height=1,
            )
            s.add(pg)
            await s.flush()
            blk = Block(
                page_id=pg.id,
                block_local_id="b1",
                type="text",
                bbox_json="[0,0,1,1]",
                order_idx=1,
                original_text="hi",
            )
            s.add(blk)
            await s.flush()
            s.add(
                BlockEmbedding(
                    block_id=blk.id,
                    model="m",
                    dim=8,
                    vector=np.ones(8, dtype=np.float32).tobytes(),
                    source_hash="h",
                    updated_at=datetime.now(UTC),
                )
            )
            await s.commit()
            blk_id = blk.id
        doc_id = await _seed_translated_chunks(factory)
        async with factory() as s:
            await backfill_chunks(s, _MockEmbed(), doc_id=doc_id)
        async with factory() as s:
            be = await s.get(BlockEmbedding, blk_id)
            assert be is not None and be.source_hash == "h"  # 1.x intact
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_chunk_embedding_cascade_on_document_delete(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _seed_translated_chunks(factory)
        async with factory() as s:
            await backfill_chunks(s, _MockEmbed(), doc_id=doc_id)
        # Delete the document → chunks → chunk_translations + chunk_embeddings cascade.
        async with factory() as s:
            doc = await s.get(Document, doc_id)
            await s.delete(doc)
            await s.commit()
        async with factory() as s:
            from sqlalchemy import func, select

            ce = (await s.execute(select(func.count()).select_from(ChunkEmbedding))).scalar()
            ct = (await s.execute(select(func.count()).select_from(ChunkTranslation))).scalar()
            ch = (await s.execute(select(func.count()).select_from(Chunk))).scalar()
        assert ce == 0 and ct == 0 and ch == 0
    finally:
        await engine.dispose()
