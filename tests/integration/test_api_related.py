"""Phase 7a — ``GET /blocks/{id}/related`` endpoint tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.db.session import make_engine, make_session_factory
from ht_lens.embedding.service import MockEmbeddingClient, text_source_hash
from ht_lens.embedding.store import upsert_embedding

from ._api_helpers import make_test_client


async def _seed_two_doc_corpus(factory: async_sessionmaker, tmp_dir: Path) -> int:
    """Returns the doc_id of doc 1 (used as the query target source)."""
    from PIL import Image

    client = MockEmbeddingClient(dim=32)
    async with factory() as session:
        for doc_id in (1, 2):
            img = tmp_dir / f"p{doc_id}.png"
            Image.new("RGB", (200, 300), color="white").save(img, "PNG")
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
                bg_image_path=str(img),
                rotation=0,
                render_dpi=200,
                pixel_width=1000,
                pixel_height=1400,
            )
            session.add(page)
            await session.flush()
            for i in range(3):
                text = (
                    f"Shared paragraph idx {i} long enough for vector "
                    "search and related-endpoint coverage."
                )
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
    return 1


def test_related_503_when_embedding_unavailable(api_db_path: Path, tmp_path: Path) -> None:
    import asyncio

    engine = make_engine(api_db_path)

    async def _seed() -> None:
        factory = make_session_factory(engine)
        await _seed_two_doc_corpus(factory, tmp_path)
        await engine.dispose()

    asyncio.run(_seed())

    # No embedding_override → DI returns None (RAG_DISABLED in helper).
    with make_test_client(api_db_path) as client:
        resp = client.get("/blocks/1/related")
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"]


def test_related_returns_cross_doc_hits(api_db_path: Path, tmp_path: Path) -> None:
    import asyncio

    engine = make_engine(api_db_path)

    async def _seed() -> None:
        factory = make_session_factory(engine)
        await _seed_two_doc_corpus(factory, tmp_path)
        await engine.dispose()

    asyncio.run(_seed())

    client = MockEmbeddingClient(dim=32)
    with make_test_client(api_db_path, embedding_override=client) as test_client:
        resp = test_client.get("/blocks/1/related?k=3&threshold=0.0")
    assert resp.status_code == 200
    hits = resp.json()
    assert hits, "expected cross-doc results"
    # All hits must come from doc 2 (exclude same-doc).
    assert all(h["doc_id"] == 2 for h in hits)
    # The first hit is the exact-text match — score should be near 1.0.
    top = max(hits, key=lambda h: h["score"])
    assert top["score"] > 0.99
    assert top["doc_filename"] == "doc2.pdf"
    assert top["page_num"] == 1
    assert "translated_preview" in top


def test_related_404_for_unknown_block(api_db_path: Path, tmp_path: Path) -> None:
    import asyncio

    engine = make_engine(api_db_path)

    async def _seed() -> None:
        factory = make_session_factory(engine)
        await _seed_two_doc_corpus(factory, tmp_path)
        await engine.dispose()

    asyncio.run(_seed())

    client = MockEmbeddingClient(dim=32)
    with make_test_client(api_db_path, embedding_override=client) as test_client:
        resp = test_client.get("/blocks/99999/related")
    assert resp.status_code == 404


def test_related_400_when_k_invalid(api_db_path: Path, tmp_path: Path) -> None:
    import asyncio

    engine = make_engine(api_db_path)

    async def _seed() -> None:
        factory = make_session_factory(engine)
        await _seed_two_doc_corpus(factory, tmp_path)
        await engine.dispose()

    asyncio.run(_seed())

    client = MockEmbeddingClient(dim=32)
    with make_test_client(api_db_path, embedding_override=client) as test_client:
        resp = test_client.get("/blocks/1/related?k=0")
        assert resp.status_code == 400
        resp = test_client.get("/blocks/1/related?k=999")
        assert resp.status_code == 400
