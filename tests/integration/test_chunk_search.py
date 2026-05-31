"""Phase 8d-2b — chunk vector search machine (seeded deterministic vectors).

Cross-lingual *quality* (bge-m3 ko→en) is validated separately by the
``@pytest.mark.llm`` test below + the live eval; these tests lock the
search *mechanics* with hand-seeded vectors (fast, no model load).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from ht_lens.db.models import Chunk, ChunkEmbedding, Document
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.chunk_search import search_chunks
from ht_lens.embedding.lookup import get_or_encode_chunk_vector
from ht_lens.embedding.service import text_source_hash
from ht_lens.embedding.store import load_all_chunks, vector_to_bytes


def _unit(*xs: float) -> np.ndarray:
    a = np.asarray(xs, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return a / n if n else a


async def _seed(db_path: Path, docs: list[list[tuple[str, np.ndarray | None]]]) -> list[list[int]]:
    """docs[d] = [(content, vector|None), ...]; returns chunk ids per doc."""
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            out: list[list[int]] = []
            for d, chunks in enumerate(docs):
                doc = Document(
                    filename=f"d{d}.pdf",
                    src_lang="en",
                    tgt_lang="ko",
                    status="translated",
                    created_at=datetime.now(UTC),
                    extractor="mineru",
                )
                s.add(doc)
                await s.flush()
                ids: list[int] = []
                for j, (content, vec) in enumerate(chunks):
                    ch = Chunk(
                        doc_id=doc.id,
                        page_idx=0,
                        order_idx=j,
                        type="text",
                        bbox_json="[]",
                        content=content,
                    )
                    s.add(ch)
                    await s.flush()
                    ids.append(ch.id)
                    if vec is not None:
                        s.add(
                            ChunkEmbedding(
                                chunk_id=ch.id,
                                model="fake",
                                dim=int(vec.shape[0]),
                                vector=vector_to_bytes(vec),
                                source_hash=text_source_hash(content),
                                updated_at=datetime.now(UTC),
                            )
                        )
                await s.commit()
                out.append(ids)
            return out
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_search_chunks_within_and_cross(api_db_path: Path) -> None:
    # doc0: A≈x-axis, B≈y-axis; doc1: C≈x-axis (same topic as A).
    ids = await _seed(
        api_db_path,
        [
            [("alpha vector content one", _unit(1, 0)), ("beta vector content two", _unit(0, 1))],
            [("gamma vector content three", _unit(0.97, 0.24))],
        ],
    )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    q = _unit(1, 0)  # closest to A (doc0[0]) and C (doc1[0])
    try:
        async with factory() as s:
            # within-section: restrict to doc0's chunks → only A/B candidates.
            within = await search_chunks(
                s, query_vector=q, top_k=5, threshold=0.1, within_chunk_ids=set(ids[0])
            )
            # cross-doc: exclude doc0 → only doc1's C.
            cross = await search_chunks(
                s, query_vector=q, top_k=5, threshold=0.1, exclude_doc_ids={1}
            )
    finally:
        await engine.dispose()
    assert within[0].chunk_id == ids[0][0]  # A ranks first
    assert all(h.chunk_id in set(ids[0]) for h in within)  # confined to the section
    assert [h.chunk_id for h in cross] == [ids[1][0]]  # only the OTHER doc's chunk


@pytest.mark.asyncio
async def test_load_all_chunks_mixed_dim_keeps_ids_matrix_aligned(api_db_path: Path) -> None:
    """Mirror the block-search desync bug: a wrong-dim row must not shift the
    ids↔matrix alignment (challenge R8)."""
    ids = await _seed(
        api_db_path,
        [
            [
                ("majority dim chunk a", _unit(1, 0)),
                ("majority dim chunk b", _unit(0, 1)),
                ("outlier dim chunk c", _unit(1, 0, 0)),  # dim 3 — the minority
            ]
        ],
    )
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            chunk_ids, matrix, _ = await load_all_chunks(s)
    finally:
        await engine.dispose()
    assert matrix.shape == (2, 2)  # majority dim 2, outlier dropped
    assert set(chunk_ids) == {ids[0][0], ids[0][1]}  # ids aligned, outlier excluded
    assert ids[0][2] not in chunk_ids


@pytest.mark.asyncio
async def test_get_or_encode_chunk_vector_reuses_stored(api_db_path: Path) -> None:
    ids = await _seed(api_db_path, [[("stored content", _unit(0.6, 0.8))]])

    class _Boom:
        dim = 2

        def encode(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
            raise AssertionError("must reuse stored vector, not encode")

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            chunk = await s.get(Chunk, ids[0][0])
            vec = await get_or_encode_chunk_vector(s, _Boom(), chunk)  # type: ignore[arg-type]
    finally:
        await engine.dispose()
    assert np.allclose(vec, _unit(0.6, 0.8), atol=1e-6)  # stored vector reused (no encode)


@pytest.mark.asyncio
async def test_search_chunks_graceful_empty_and_dim_mismatch(api_db_path: Path) -> None:
    ids = await _seed(api_db_path, [[("only chunk", _unit(1, 0))]])
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            # wrong-dim query → [] (never raises; challenge R6)
            assert await search_chunks(s, query_vector=_unit(1, 0, 0), threshold=0.1) == []
            # zero query → []
            assert await search_chunks(s, query_vector=np.zeros(2, np.float32), threshold=0.1) == []
            # min_chars drops the short chunk
            hi = await search_chunks(s, query_vector=_unit(1, 0), threshold=0.1, min_chars=100)
    finally:
        await engine.dispose()
    assert hi == []  # "only chunk" (10 chars) dropped by min_chars=100
    assert ids  # seeded


@pytest.mark.asyncio
async def test_search_chunks_empty_corpus(api_db_path: Path) -> None:
    await _seed(api_db_path, [[("no embedding here", None)]])  # chunk but no embedding
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            assert await search_chunks(s, query_vector=_unit(1, 0), threshold=0.1) == []
    finally:
        await engine.dispose()
