"""Phase 3 — /documents/{id}/pages and /image endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ht_lens.db.models import Page
from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


@pytest.mark.asyncio
async def test_get_page_returns_blocks(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(
            session, tmp_dir=tmp_path, blocks_per_page=3, num_pages=1
        )
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page_num"] == 1
    assert len(body["blocks"]) == 3
    first = body["blocks"][0]
    assert first["block_local_id"] == "p1_b001"
    assert first["translated_text"].startswith("페이지")
    assert first["has_thread"] is False
    assert body["render"]["pixel_w"] == 200


@pytest.mark.asyncio
async def test_get_page_404_for_unknown_doc(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/documents/123/pages/1")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "document not found"


@pytest.mark.asyncio
async def test_get_page_404_for_unknown_page(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/9")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "page not found"


@pytest.mark.asyncio
async def test_get_page_image_streams_png(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/1/image")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert "max-age" in resp.headers["cache-control"]
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_get_page_image_serves_ingested_absolute_path(
    api_db_path: Path, tmp_path: Path
) -> None:
    """The PNG path stored by ingest is an absolute /tmp path; serve it as-is."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    assert seeded.image_paths[0].is_absolute()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/1/image")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_page_image_500_when_path_outside_or_missing(
    api_db_path: Path, tmp_path: Path
) -> None:
    """Corrupted DB row (file deleted on disk) should respond 500, not crash."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
        # delete the file referenced by DB
        seeded.image_paths[0].unlink()
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/1/image")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_page_image_rejects_traversal_path(api_db_path: Path, tmp_path: Path) -> None:
    """Operator-set bg_image_path containing ``..`` is refused with 500."""
    from sqlalchemy import update

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
        # forcibly set a traversal-style path on the page row
        await session.execute(
            update(Page)
            .where(Page.id == seeded.page_ids[0])
            .values(bg_image_path=str(tmp_path / ".." / "evil.png"))
        )
        await session.commit()
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/1/image")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_page_bbox_is_list_of_floats(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=2)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/1")
    body = resp.json()
    bbox = body["blocks"][0]["bbox"]
    assert isinstance(bbox, list)
    assert len(bbox) == 4
    assert all(isinstance(v, int | float) for v in bbox)
    # round-trip with json so we make sure schema accepts list (not tuple)
    json.dumps(bbox)


@pytest.mark.asyncio
async def test_get_page_serializes_table_block_type(api_db_path: Path, tmp_path: Path) -> None:
    """``BlockRead.type`` Literal must include ``table`` (roadmap §schema).

    Phase 1 does not yet emit ``table`` blocks, but Phase 6 will. This locks
    the API response schema so future ingest does not silently 500 on
    pydantic validation.
    """
    from sqlalchemy import update

    from ht_lens.db.models import Block

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=2)
        # Force the first block's type to "table" — simulates Phase 6 ingest.
        await session.execute(
            update(Block).where(Block.id == seeded.block_ids[0]).values(type="table")
        )
        await session.commit()
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages/1")
    assert resp.status_code == 200
    body = resp.json()
    types = [b["type"] for b in body["blocks"]]
    assert "table" in types
