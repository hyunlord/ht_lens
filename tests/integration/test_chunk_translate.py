"""Phase 8b — chunk translation pipeline integration tests.

MockLLMClient.translate returns ``"[KO] <text>"`` and preserves its input
(so ⟦MATHi⟧ placeholders survive → restore is byte-identical). Custom
mocks below cover the math-lost-failed path and cache-dedup counting.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ht_lens.db.models import Block, Chunk, ChunkTranslation, Document, Translation
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.chunk_pipeline import translate_chunks


async def _factory(db_path):  # type: ignore[no-untyped-def]
    engine = make_engine(db_path)
    return engine, make_session_factory(engine)


async def _make_doc(factory, chunks: list[dict]) -> int:  # type: ignore[no-untyped-def]
    async with factory() as s:
        doc = Document(
            filename="m.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            extractor="mineru",
        )
        s.add(doc)
        await s.flush()
        for i, c in enumerate(chunks):
            s.add(
                Chunk(
                    doc_id=doc.id,
                    page_idx=c.get("page_idx", 0),
                    order_idx=i,
                    type=c["type"],
                    text_level=c.get("text_level"),
                    bbox_json="[0,0,1,1]",
                    content=c.get("content", ""),
                    text_format=c.get("text_format"),
                    img_path=c.get("img_path"),
                    caption=c.get("caption"),
                )
            )
        await s.commit()
        return doc.id


@pytest.mark.asyncio
async def test_text_translated_with_math_preserved(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [{"type": "text", "content": r"Use $p(z)=\operatorname*{Dir}(z|\alpha)$ here."}],
        )
        async with factory() as s:
            stats = await translate_chunks(doc_id, s, MockLLMClient())
        assert stats.translated == 1
        async with factory() as s:
            from sqlalchemy import select

            tr = (await s.execute(select(ChunkTranslation))).scalar_one()
        # Math byte-identical, no leftover placeholder, KO prefix from mock.
        assert r"$p(z)=\operatorname*{Dir}(z|\alpha)$" in tr.translated_text
        assert "⟦MATH" not in tr.translated_text
        assert tr.translated_text.startswith("[KO]")
        assert tr.status == "translated"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_equation_passthrough_no_llm(api_db_path) -> None:  # type: ignore[no-untyped-def]
    calls = {"n": 0}

    class CountingMock(MockLLMClient):
        async def translate(self, text, src, tgt, *, context=None):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return await super().translate(text, src, tgt, context=context)

    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [{"type": "equation", "content": r"$$E=mc^2$$", "text_format": "latex"}],
        )
        async with factory() as s:
            stats = await translate_chunks(doc_id, s, CountingMock())
        assert stats.passthrough == 1 and calls["n"] == 0
        async with factory() as s:
            from sqlalchemy import select

            tr = (await s.execute(select(ChunkTranslation))).scalar_one()
        assert tr.translated_text == r"$$E=mc^2$$"  # verbatim
        assert tr.model == "passthrough"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_image_caption_and_chart_content_translated(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [
                {
                    "type": "image",
                    "content": "",
                    "img_path": "images/f.jpg",
                    "caption": "Figure 1: a cat",
                },
                {
                    "type": "image",
                    "content": "bar chart values",
                    "img_path": "images/c.jpg",
                    "caption": "Chart 2",
                },
            ],
        )
        async with factory() as s:
            await translate_chunks(doc_id, s, MockLLMClient())
        async with factory() as s:
            from sqlalchemy import select

            trs = list(
                (
                    await s.execute(select(ChunkTranslation).order_by(ChunkTranslation.chunk_id))
                ).scalars()
            )
        fig, chart = trs
        assert fig.translated_text == ""  # pure image, no body
        assert fig.caption_translated == "[KO] Figure 1: a cat"
        assert chart.translated_text == "[KO] bar chart values"  # chart content NOT dropped
        assert chart.caption_translated == "[KO] Chart 2"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cache_dedup_one_llm_call_for_identical_content(api_db_path) -> None:  # type: ignore[no-untyped-def]
    calls = {"n": 0}

    class CountingMock(MockLLMClient):
        async def translate(self, text, src, tgt, *, context=None):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            return await super().translate(text, src, tgt, context=context)

    engine, factory = await _factory(api_db_path)
    try:
        # Three chunks, two identical → 2 unique LLM calls (5.66x dedup).
        doc_id = await _make_doc(
            factory,
            [
                {"type": "text", "content": "Repeated paragraph about latent factors."},
                {"type": "text", "content": "Repeated paragraph about latent factors."},
                {"type": "text", "content": "A different paragraph entirely here."},
            ],
        )
        async with factory() as s:
            stats = await translate_chunks(doc_id, s, CountingMock(), concurrency=7)
        assert stats.translated == 3
        assert calls["n"] == 2, f"expected dedup to 2 unique calls, got {calls['n']}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_math_lost_marks_chunk_failed(api_db_path) -> None:  # type: ignore[no-untyped-def]
    class DroppingMock(MockLLMClient):
        async def translate(self, text, src, tgt, *, context=None):  # type: ignore[no-untyped-def]
            # Strip placeholders to simulate an LLM that drops them.
            import re

            return "[KO] " + re.sub(r"⟦MATH\d+⟧", "", text)

    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(factory, [{"type": "text", "content": "Has $x^2$ math."}])
        async with factory() as s:
            stats = await translate_chunks(doc_id, s, DroppingMock())
        assert stats.failed == 1 and stats.translated == 0
        async with factory() as s:
            from sqlalchemy import select

            tr = (await s.execute(select(ChunkTranslation))).scalar_one()
        assert tr.status == "failed"
        # Content NOT mutated with append-comment fakery.
        assert "누락" not in tr.translated_text and "MATH" not in tr.translated_text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cache_key_includes_src_tgt_model(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory, [{"type": "text", "content": "Latent factor models intro."}]
        )
        async with factory() as s:
            await translate_chunks(doc_id, s, MockLLMClient())
        async with factory() as s:
            from sqlalchemy import select

            from ht_lens.translate.cache import cache_key

            tr = (await s.execute(select(ChunkTranslation))).scalar_one()
        # cache_key is the full 4-tuple over the ORIGINAL content.
        expected = cache_key("Latent factor models intro.", "en", "ko", "mock")
        assert tr.cache_key == expected
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_skips_already_translated(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(factory, [{"type": "text", "content": "Some body text here now."}])
        async with factory() as s:
            await translate_chunks(doc_id, s, MockLLMClient())
        async with factory() as s:
            stats2 = await translate_chunks(doc_id, s, MockLLMClient())
        assert stats2.skipped == 1 and stats2.translated == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_1x_translations_untouched(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        # Seed a 1.x block + translation.
        async with factory() as s:
            from ht_lens.db.models import Page

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
                Translation(
                    block_id=blk.id,
                    translated_text="안녕",
                    model="m",
                    status="translated",
                    updated_at=datetime.now(UTC),
                )
            )
            await s.commit()
            blk_id = blk.id
        doc_id = await _make_doc(factory, [{"type": "text", "content": "mineru chunk body text."}])
        async with factory() as s:
            await translate_chunks(doc_id, s, MockLLMClient())
        async with factory() as s:
            tr = await s.get(Translation, blk_id)
            assert tr is not None and tr.translated_text == "안녕"  # 1.x intact
    finally:
        await engine.dispose()
