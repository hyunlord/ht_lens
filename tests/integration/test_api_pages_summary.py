"""Phase 6b — GET /documents/{id}/pages-summary endpoint tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ht_lens.db.models import Page
from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


@pytest.mark.asyncio
async def test_pages_summary_404_for_unknown_doc(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/documents/9999/pages-summary")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pages_summary_returns_one_entry_per_page_in_order(
    api_db_path: Path, tmp_path: Path
) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, num_pages=3)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    assert [p["page_num"] for p in body] == [1, 2, 3]
    # Each summary carries the render block needed for placeholder height.
    for p in body:
        assert {"page_num", "width", "height", "rotation", "render"} <= p.keys()
        assert {"dpi", "pixel_w", "pixel_h", "scale"} <= p["render"].keys()


@pytest.mark.asyncio
async def test_pages_summary_preserves_rotation_and_render_dims_per_page(
    api_db_path: Path, tmp_path: Path
) -> None:
    """Phase 6b debate §5: placeholder rows must size accurately even when
    page rotation/dimensions vary. Patch one page with non-zero rotation
    and verify it survives the response."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, num_pages=2)
        await session.execute(
            Page.__table__.update().where(Page.id == seeded.page_ids[1]).values(rotation=90)
        )
        await session.commit()
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages-summary")
    body = resp.json()
    rotations = {p["page_num"]: p["rotation"] for p in body}
    assert rotations == {1: 0, 2: 90}


@pytest.mark.asyncio
async def test_pages_summary_handles_mixed_page_sizes(api_db_path: Path, tmp_path: Path) -> None:
    """Mixed page dimensions (some letter-sized, some larger) must each be
    returned independently so the viewer can compute different placeholder
    heights."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, num_pages=2)
        # Stretch page 2 to A3 dimensions (1191 x 1684 pt).
        await session.execute(
            Page.__table__.update()
            .where(Page.id == seeded.page_ids[1])
            .values(
                width=1191.0,
                height=1684.0,
                pixel_width=3508,
                pixel_height=4961,
            )
        )
        await session.commit()
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages-summary")
    body = resp.json()
    page1, page2 = body[0], body[1]
    assert page1["width"] != page2["width"]
    assert page2["width"] == 1191.0
    assert page2["render"]["pixel_w"] == 3508
    # Scale recomputed per page: pixel_w / width.
    assert abs(page1["render"]["scale"] - page1["render"]["pixel_w"] / page1["width"]) < 1e-6
    assert abs(page2["render"]["scale"] - page2["render"]["pixel_w"] / page2["width"]) < 1e-6


@pytest.mark.asyncio
async def test_pages_summary_does_not_include_blocks(api_db_path: Path, tmp_path: Path) -> None:
    """Summary endpoint must stay lightweight — no block payload."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=10)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}/pages-summary")
    body = resp.json()
    for p in body:
        assert "blocks" not in p
        assert "block_count" not in p  # decision: dropped during challenge
