"""Phase 8d-2c — neighbour-context short-chunk re-translation tests.

Locks the four risks the challenge (R1/R3/R4/R5/R6/R7) and Codex's debate
flagged:
- selection excludes reference numbers / math, NOT by a repeat count (R4/R5/R6);
- neighbours are all-type labelled, so the equation a "where" refers to is in
  context (R7);
- a re-translation writes ``cache_key=NULL`` so it cannot poison the
  content-only cache a future identical-source chunk reuses (R1, CRITICAL);
- a malformed / placeholder-losing LLM output PRESERVES the existing row (R3).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from ht_lens.db.models import Chunk, ChunkTranslation, Document
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.llm.mock import MockLLMClient
from ht_lens.translate.chunk_pipeline import _db_cache_lookup, make_cache_key, translate_chunks
from ht_lens.translate.short_retranslate import (
    _neighbor_context,
    is_math_dense,
    is_reference_number,
    retranslate_short,
    select_short_retranslate,
)


async def _factory(db_path):  # type: ignore[no-untyped-def]
    engine = make_engine(db_path)
    return engine, make_session_factory(engine)


async def _make_doc(factory, chunks: list[dict]) -> int:  # type: ignore[no-untyped-def]
    """Insert a doc + chunks; each chunk dict may carry a ``tr`` sub-dict
    (text/status/cache_key) to seed a ChunkTranslation directly."""
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
            chunk = Chunk(
                doc_id=doc.id,
                page_idx=0,
                order_idx=i,
                type=c["type"],
                text_level=c.get("text_level"),
                bbox_json="[0,0,1,1]",
                content=c.get("content", ""),
                text_format=c.get("text_format"),
            )
            s.add(chunk)
            await s.flush()
            ids.append(chunk.id)
            tr = c.get("tr")
            if tr is not None:
                s.add(
                    ChunkTranslation(
                        chunk_id=chunk.id,
                        translated_text=tr["text"],
                        caption_translated=None,
                        model="mock",
                        cache_key=tr.get("cache_key"),
                        status=tr.get("status", "translated"),
                        updated_at=datetime.now(UTC),
                    )
                )
        await s.commit()
        return doc.id


async def _load(factory, doc_id):  # type: ignore[no-untyped-def]
    async with factory() as s:
        chunks = list(
            (
                await s.execute(
                    select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.order_idx)
                )
            ).scalars()
        )
        trs = {t.chunk_id: t for t in (await s.execute(select(ChunkTranslation))).scalars()}
    return chunks, trs


# --------------------------------------------------------------------------- #
# Pure selectors (no DB)
# --------------------------------------------------------------------------- #
def test_is_reference_number_targets_numbers_not_short_text() -> None:
    for ref in ["(28.116)", "28.4.2", "Eq. 3", "Eq. (3.1)", "Fig. 2", "Table 1", "[12]", "(A.1)"]:
        assert is_reference_number(ref), ref
    # NOT reference numbers — short text that contains digits (R5: no digit-ratio).
    for txt in ["where", "K=10", "p=0.5", "N samples", "as follows:"]:
        assert not is_reference_number(txt), txt


def test_is_math_dense_covers_dollar_and_latex_delimiters() -> None:
    assert is_math_dense(r"$x_i$")
    assert is_math_dense(r"value \(a+b\) here")
    assert is_math_dense(r"\[ E = mc^2 \]")
    assert not is_math_dense("where")
    assert not is_math_dense("as follows:")


def test_neighbor_context_includes_all_types_labelled() -> None:
    chunks = [
        Chunk(type="heading", content="28.4 Variational Inference", order_idx=0),
        Chunk(type="text", content="where", order_idx=1),
        Chunk(type="equation", content="$$q(z)=\\prod_i q_i$$", order_idx=2),
    ]
    ctx = _neighbor_context(chunks, 1, radius=1)
    # both neighbours present, labelled, target itself excluded (R7).
    assert "[섹션] 28.4 Variational Inference" in ctx
    assert "[수식] $$q(z)=\\prod_i q_i$$" in ctx
    assert "where" not in ctx.replace("[수식]", "").replace("[섹션]", "")


# --------------------------------------------------------------------------- #
# Selection (DB)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_select_short_retranslate_includes_where_excludes_others(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [
                {"type": "text", "content": "where", "tr": {"text": "[KO] where"}},  # IN
                {"type": "text", "content": "(28.116)", "tr": {"text": "(28.116)"}},  # OUT ref
                {"type": "text", "content": r"$x_i$", "tr": {"text": r"$x_i$"}},  # OUT math
                {"type": "text", "content": "x" * 40, "tr": {"text": "[KO] long"}},  # OUT len>=25
                {
                    "type": "text",
                    "content": "broken",
                    "tr": {"text": "", "status": "failed"},
                },  # OUT failed
                {
                    "type": "heading",
                    "content": "Intro",
                    "tr": {"text": "[KO] Intro"},
                },  # OUT not text
            ],
        )
        chunks, trs = await _load(factory, doc_id)
        picked = select_short_retranslate(chunks, trs, max_chars=25)
        assert [c.content for c in picked] == ["where"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_short_retranslate_duplicate_where_not_excluded(api_db_path) -> None:  # type: ignore[no-untyped-def]
    # R4: two legitimate repeated "where" chunks both stay candidates — no
    # count-based boilerplate exclusion (that would drop exactly what we fix).
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [
                {"type": "text", "content": "where", "tr": {"text": "[KO] where"}},
                {"type": "equation", "content": "$$a$$", "text_format": "latex"},
                {"type": "text", "content": "where", "tr": {"text": "[KO] where"}},
            ],
        )
        chunks, trs = await _load(factory, doc_id)
        picked = select_short_retranslate(chunks, trs, max_chars=25)
        assert len(picked) == 2
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# Re-translation behaviour (DB + LLM)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_short_retranslate_writes_null_cache_key_no_poison(api_db_path) -> None:  # type: ignore[no-untyped-def]
    """CRITICAL (R1): a context-specific re-translation must be invisible to the
    content-only cache, else a future identical "where" reuses it."""

    class _ContextMock(MockLLMClient):
        async def translate(self, text, src, tgt, *, context=None):  # type: ignore[no-untyped-def]
            return f"[CTX] {text}" if context else f"[{tgt.upper()}] {text}"

    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [
                {"type": "text", "content": "where"},
                {"type": "equation", "content": "$$q(z)$$", "text_format": "latex"},
            ],
        )
        # 1) normal translation → content cache key populated, cache active.
        async with factory() as s:
            await translate_chunks(doc_id, s, MockLLMClient())
        ck = make_cache_key("where", "en", "ko", "mock")
        async with factory() as s:
            assert await _db_cache_lookup(s, ck) == "[KO] where"  # baseline

        # 2) neighbour re-translation overwrites → cache_key NULL.
        async with factory() as s:
            doc = (await s.execute(select(Document).where(Document.id == doc_id))).scalar_one()
            stats = await retranslate_short(s, doc, _ContextMock(), max_chars=25)
        assert stats.retranslated == 1

        async with factory() as s:
            chunks, trs = await _load(factory, doc_id)
            where_id = next(c.id for c in chunks if c.content == "where")
            row = trs[where_id]
            assert row.translated_text == "[CTX] where"  # used neighbour context
            assert row.cache_key is None  # R1: not cacheable
            # poison check: the content cache can no longer serve the where row.
            assert await _db_cache_lookup(s, ck) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_short_retranslate_malformed_llm_preserves_existing(api_db_path) -> None:  # type: ignore[no-untyped-def]
    """R3: empty output or a dropped math placeholder leaves the existing row
    untouched and counts as failed (no silent degradation)."""

    class _EmptyMock(MockLLMClient):
        async def translate(self, text, src, tgt, *, context=None):  # type: ignore[no-untyped-def]
            return "   "  # whitespace → treated as empty

    class _DropMathMock(MockLLMClient):
        async def translate(self, text, src, tgt, *, context=None):  # type: ignore[no-untyped-def]
            return "번역됨"  # drops the ⟦MATH0⟧ placeholder entirely

    # The math case is forced via chunk_ids because the auto-selector EXCLUDES
    # math-dense chunks — the placeholder-loss path is only reachable when a
    # user explicitly targets a math chunk with --chunk-id. The empty-output
    # case uses a normal short text chunk.
    for mock, content, seed in (
        (_EmptyMock(), "where", "[KO] where"),
        (_DropMathMock(), r"see $x$", "[KO] see $x$"),
    ):
        engine, factory = await _factory(api_db_path)
        try:
            doc_id = await _make_doc(
                factory,
                [
                    {"type": "text", "content": content, "tr": {"text": seed}},
                    {
                        "type": "text",
                        "content": "a sufficiently long neighbour paragraph for context.",
                        "tr": {"text": "[KO] ctx"},
                    },
                ],
            )
            chunks, _ = await _load(factory, doc_id)
            target_id = chunks[0].id
            async with factory() as s:
                doc = (await s.execute(select(Document).where(Document.id == doc_id))).scalar_one()
                stats = await retranslate_short(s, doc, mock, chunk_ids={target_id})
            assert stats.failed == 1
            assert stats.retranslated == 0
            _, trs = await _load(factory, doc_id)
            assert trs[target_id].translated_text == seed  # PRESERVED
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_short_retranslate_dry_run_writes_nothing(api_db_path) -> None:  # type: ignore[no-untyped-def]
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [
                {"type": "text", "content": "where", "tr": {"text": "[KO] where"}},
                # ≥25 chars so it is NOT itself a candidate — just neighbour context.
                {
                    "type": "text",
                    "content": "a sufficiently long neighbour paragraph.",
                    "tr": {"text": "[KO] c"},
                },
            ],
        )
        async with factory() as s:
            doc = (await s.execute(select(Document).where(Document.id == doc_id))).scalar_one()
            stats = await retranslate_short(s, doc, MockLLMClient(), max_chars=25, dry_run=True)
        assert stats.candidates == 1
        assert stats.retranslated == 0  # dry-run never writes
        assert len(stats.previews) == 1
        cid, before, after = stats.previews[0]
        assert before == "[KO] where"
        assert after.startswith("[KO]")
        # DB untouched.
        _, trs = await _load(factory, doc_id)
        assert trs[cid].translated_text == "[KO] where"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_short_retranslate_explicit_chunk_id_path(api_db_path) -> None:  # type: ignore[no-untyped-def]
    # R8: --chunk-id targets a chunk even if the auto-selector would skip it
    # (here a 40-char chunk that the length bound excludes).
    engine, factory = await _factory(api_db_path)
    try:
        doc_id = await _make_doc(
            factory,
            [{"type": "text", "content": "x" * 40, "tr": {"text": "[KO] old", "cache_key": "k"}}],
        )
        chunks, _ = await _load(factory, doc_id)
        target_id = chunks[0].id
        async with factory() as s:
            doc = (await s.execute(select(Document).where(Document.id == doc_id))).scalar_one()
            stats = await retranslate_short(s, doc, MockLLMClient(), chunk_ids={target_id})
        assert stats.retranslated == 1
        _, trs = await _load(factory, doc_id)
        assert trs[target_id].cache_key is None  # still NULL-keyed (R1)
        assert trs[target_id].translated_text.startswith("[KO]")
    finally:
        await engine.dispose()
