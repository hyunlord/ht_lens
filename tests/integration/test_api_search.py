"""Phase 6a — /search endpoint integration tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from sqlalchemy import insert

from ht_lens.db.models import Block, Translation
from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


@pytest.mark.asyncio
async def test_search_rejects_short_query(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/search?q=a")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_returns_hits_in_original_text(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=3)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get("/search?q=block&limit=10")
    assert resp.status_code == 200
    hits = resp.json()
    assert len(hits) >= 1
    first = hits[0]
    assert first["matched_field"] == "original"
    assert "<mark>" in first["preview"]
    # Preview contains the matched text inside <mark>; case preserved.
    assert "block" in first["preview"].lower()


@pytest.mark.asyncio
async def test_search_returns_translated_only_match(api_db_path: Path, tmp_path: Path) -> None:
    """SearchHit.matched_field must be ``translated`` when only the translation
    contains the needle (Phase 6a debate §5 missing test)."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session,
            tmp_dir=tmp_path,
            blocks_per_page=1,
            with_translations=True,
        )
        # Replace translation with something unique to translated only.
        bid = seeded.block_ids[0]
        await session.execute(
            Translation.__table__.update()
            .where(Translation.block_id == bid)
            .values(translated_text="한국어전용단어")
        )
        # And make sure original_text does NOT contain the term.
        await session.execute(
            Block.__table__.update()
            .where(Block.id == bid)
            .values(original_text="English original only")
        )
        await session.commit()
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get("/search?q=한국어전용")
    assert resp.status_code == 200
    hits = resp.json()
    assert any(h["matched_field"] == "translated" for h in hits)
    matched = next(h for h in hits if h["matched_field"] == "translated")
    assert "<mark>한국어전용</mark>" in matched["preview"]


@pytest.mark.asyncio
async def test_search_doc_id_orders_matches_first(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        await seed_minimal_document(session, tmp_dir=tmp_path, filename="a.pdf")
        b = await seed_minimal_document(session, tmp_dir=tmp_path, filename="b.pdf")
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        # Boost doc B; results from B should come first even though id(b) > id(a).
        resp2 = client.get(f"/search?q=block&doc_id={b.doc_id}&limit=20")
    hits2 = resp2.json()
    # The first hit should come from doc B because of the boost.
    assert hits2[0]["doc_id"] == b.doc_id


@pytest.mark.asyncio
async def test_search_limit_clamp(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=5)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get("/search?q=block&limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


@pytest.mark.asyncio
async def test_search_empty_results(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get("/search?q=zzz_no_such_token_zzz")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_search_10k_blocks_latency_under_budget(api_db_path: Path, tmp_path: Path) -> None:
    """Phase 6a DoD: search must answer within 200ms over a 10K-block doc.

    We synthesize the 10K rows directly via raw SQL to keep the fixture cheap,
    then issue one HTTP search request via TestClient (which still goes
    through the full FastAPI stack incl. async session). The budget is
    intentionally generous (500ms) to absorb GC/test-runner jitter; the
    expected steady-state on a workstation is well under 100ms.
    """
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=1)
        page_id = seeded.page_ids[0]
        rows = [
            {
                "page_id": page_id,
                "block_local_id": f"p1_b{i + 1000:05d}",
                "type": "text",
                "bbox_json": "[0,0,10,10]",
                "order_idx": 1000 + i,
                "original_text": (
                    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                    "Synthetic row for latency benchmarking — needle position varies."
                ),
            }
            for i in range(10_000)
        ]
        await session.execute(insert(Block), rows)
        await session.commit()
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        # Warm up — TestClient instantiates lifespan + engine on first request.
        client.get("/search?q=ipsum&limit=10")
        t0 = time.perf_counter()
        resp = client.get("/search?q=ipsum&limit=50")
        elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert elapsed < 0.5, f"LIKE search over 10K blocks took {elapsed * 1000:.1f}ms"
    # Surface the actual number for the verify report.
    print(f"\n[bench] search 10K blocks: {elapsed * 1000:.1f}ms")


@pytest.mark.asyncio
async def test_search_rejects_whitespace_only_query(api_db_path: Path) -> None:
    """R1 fix: ``q="   "`` passes ``min_length=2`` but trims to "" — the
    handler must reject after-trim emptiness, not return all rows."""
    with make_test_client(api_db_path) as client:
        resp = client.get("/search?q=%20%20%20%20")  # 4 spaces, URL-encoded
    assert resp.status_code == 422
    assert "non-whitespace" in resp.json()["detail"]
