"""Phase 8d-2a — chunk chat context builder tests.

``section_chunk_range`` is exercised as a pure function (parity with the
8d-1 JS ``computeSectionChunks``); ``build_*_context`` use a seeded DB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ht_lens.api.chunk_chat_context import (
    build_chunk_context,
    build_figure_context,
    build_section_context,
    build_section_context_topk,
    parse_section_no,
    section_chunk_range,
)
from ht_lens.db.models import Chunk, ChunkTranslation, Document
from ht_lens.db.session import make_engine, make_session_factory


def _c(cid: int, ctype: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(id=cid, type=ctype, content=content)


async def _seed(db_path: Path, chunks: list[dict]) -> tuple[int, list[int]]:
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
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
            ids: list[int] = []
            for i, c in enumerate(chunks):
                ch = Chunk(
                    doc_id=doc.id,
                    page_idx=c.get("page_idx", 0),
                    order_idx=i,
                    type=c["type"],
                    text_level=c.get("text_level"),
                    bbox_json="[]",
                    content=c["content"],
                    caption=c.get("caption"),
                )
                s.add(ch)
                await s.flush()
                ids.append(ch.id)
                if "translated" in c or "caption_translated" in c:
                    s.add(
                        ChunkTranslation(
                            chunk_id=ch.id,
                            translated_text=c.get("translated", ""),
                            caption_translated=c.get("caption_translated"),
                            model="mock",
                            status=c.get("tr_status", "translated"),
                            updated_at=datetime.now(UTC),
                        )
                    )
            await s.commit()
            return doc.id, ids
    finally:
        await engine.dispose()


def test_parse_section_no_parity_with_js() -> None:
    assert parse_section_no("28.4.2 Multinomial PCA") == "28.4.2"
    assert parse_section_no("§28.4") == "28.4"
    assert parse_section_no("28.4.2. Title") == "28.4.2"
    assert parse_section_no("28 Latent Variable Models") == "28"
    assert parse_section_no("Appendix A.1") is None
    assert parse_section_no("") is None


def test_section_range_parent_includes_children() -> None:
    chunks = [
        _c(1, "heading", "28.4 C"),
        _c(2, "text", "x"),
        _c(3, "heading", "28.4.1 D"),
        _c(4, "text", "y"),
        _c(5, "heading", "28.4.2 E"),
        _c(6, "heading", "28.4.2.1 F"),
        _c(7, "heading", "28.5 G"),
    ]
    got = [c.id for c in section_chunk_range(chunks, 1)]
    assert got == [1, 2, 3, 4, 5, 6]  # 28.4 .. 28.4.2.1, stop before 28.5


def test_section_range_duplicate_secno_uses_heading_id() -> None:
    """Two '28.4' headings: anchoring by chunk id picks the right one (R1)."""
    chunks = [
        _c(1, "heading", "28.4 First"),
        _c(2, "text", "a"),
        _c(3, "heading", "28.5 Mid"),
        _c(4, "heading", "28.4 Second (appendix excerpt)"),
        _c(5, "text", "b"),
        _c(6, "heading", "28.6 End"),
    ]
    assert [c.id for c in section_chunk_range(chunks, 1)] == [1, 2]  # first 28.4
    assert [c.id for c in section_chunk_range(chunks, 4)] == [4, 5]  # second 28.4


def test_section_range_unnumbered_heading_fallback() -> None:
    chunks = [
        _c(1, "heading", "Appendix A"),
        _c(2, "text", "a"),
        _c(3, "text", "b"),
        _c(4, "heading", "References"),
    ]
    # Unnumbered → stop at the next heading of any kind.
    assert [c.id for c in section_chunk_range(chunks, 1)] == [1, 2, 3]


def test_section_range_unknown_heading_empty() -> None:
    assert section_chunk_range([_c(1, "heading", "28.4 X")], 999) == []


@pytest.mark.asyncio
async def test_build_section_context_full_small(api_db_path: Path) -> None:
    doc_id, ids = await _seed(
        api_db_path,
        [
            {"type": "heading", "content": "28.4 Sec", "translated": "[KO] 28.4 절"},
            {"type": "text", "content": "body one", "translated": "[KO] 본문 1"},
            {"type": "text", "content": "body two", "translated": "[KO] 본문 2"},
            {"type": "heading", "content": "28.5 Next", "translated": "[KO] 28.5"},
        ],
    )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            ctx = await build_section_context(s, doc_id, ids[0], budget=6000)
    finally:
        await engine.dispose()
    assert ctx.truncated is False
    assert ctx.included_chunk_ids == ids[:3]  # 28.4 + 2 body, not 28.5
    assert ctx.total_chunks == 3
    assert "[KO] 본문 1" in ctx.text and "[섹션:" in ctx.text


@pytest.mark.asyncio
async def test_build_section_context_degraded_large(api_db_path: Path) -> None:
    big = "가" * 4000
    doc_id, ids = await _seed(
        api_db_path,
        [
            {"type": "heading", "content": "28.4 Sec", "translated": "[KO] 28.4 절"},
            {"type": "text", "content": "b1", "translated": big},
            {"type": "text", "content": "b2", "translated": big},
            {"type": "text", "content": "b3", "translated": big},
            {"type": "heading", "content": "28.5 Next", "translated": "[KO] 28.5"},
        ],
    )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            ctx = await build_section_context(s, doc_id, ids[0], budget=6000)
    finally:
        await engine.dispose()
    assert ctx.truncated is True  # over budget → degraded
    assert ctx.total_chunks == 4  # heading + 3 body in the section
    assert ids[0] in ctx.included_chunk_ids  # heading always kept
    assert len(ctx.included_chunk_ids) < 4  # truncated below the full section
    assert "일부만" in ctx.text  # degraded notice present


@pytest.mark.asyncio
async def test_build_chunk_context_radius_crosses_pages(api_db_path: Path) -> None:
    _doc_id, ids = await _seed(
        api_db_path,
        [
            {"type": "text", "content": "a", "translated": "[KO] a", "page_idx": 0},
            {"type": "text", "content": "b", "translated": "[KO] b", "page_idx": 0},
            {"type": "text", "content": "c", "translated": "[KO] c", "page_idx": 1},  # next page
            {"type": "text", "content": "d", "translated": "[KO] d", "page_idx": 1},
        ],
    )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            ctx = await build_chunk_context(s, ids[1], radius=2)
    finally:
        await engine.dispose()
    # ±2 around idx1 → ids 0..3, crossing the page_idx boundary (reflow continuous).
    assert ctx.included_chunk_ids == ids[:4]
    assert "현재 문단" in ctx.text


@pytest.mark.asyncio
async def test_build_figure_context_caption_and_neighbors(api_db_path: Path) -> None:
    """Figure context = caption (translated) + ±2 neighbours; query_text is
    caption+neighbours, never the empty image content (challenge R4)."""
    _doc_id, ids = await _seed(
        api_db_path,
        [
            {"type": "text", "content": "before text", "translated": "[KO] 앞 본문"},
            {
                "type": "image",
                "content": "",  # image chunks have empty content
                "caption": "Figure 1: a cat",
                "caption_translated": "[KO] 그림 1: 고양이",
            },
            {"type": "text", "content": "after text", "translated": "[KO] 뒤 본문"},
        ],
    )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            ctx = await build_figure_context(s, ids[1], radius=2)
    finally:
        await engine.dispose()
    assert "[KO] 그림 1: 고양이" in ctx.text  # translated caption
    assert "앞 본문" in ctx.text and "뒤 본문" in ctx.text  # ±2 neighbours
    assert "그림 1: 고양이" in ctx.query_text  # cross-doc query = caption+neighbours
    assert "앞 본문" in ctx.query_text  # not the empty image content (R4)
    assert ids[1] in ctx.included_chunk_ids


@pytest.mark.asyncio
async def test_within_section_topk_empty_hits_falls_back_to_degraded(api_db_path: Path) -> None:
    """Over-budget section with NO embeddings → search returns [] → falls back
    to the 8d-2a degraded truncation (heading + budget-fit; challenge R10)."""
    big = "가" * 5000
    doc_id, ids = await _seed(
        api_db_path,
        [
            {"type": "heading", "content": "28.4 Sec", "translated": "[KO] 28.4 절"},
            {"type": "text", "content": "b1", "translated": big},
            {"type": "text", "content": "b2", "translated": big},
            {"type": "heading", "content": "28.5 Next", "translated": "[KO] 28.5"},
        ],
    )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:  # no chunk_embeddings seeded → search [] → fallback
            ctx = await build_section_context_topk(
                s,
                doc_id,
                ids[0],
                question_vector=np.array([1.0, 0.0], dtype=np.float32),
                budget=6000,
            )
    finally:
        await engine.dispose()
    assert ctx.truncated is True  # degraded
    assert ids[0] in ctx.included_chunk_ids  # heading always kept
    assert "일부만" in ctx.text  # 8d-2a degraded notice (fell back, not top-K)
