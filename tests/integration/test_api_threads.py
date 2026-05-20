"""Phase 3 — /threads endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


@pytest.mark.asyncio
async def test_create_thread_with_default_title(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, blocks_per_page=2)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.post("/threads", json={"block_id": seeded.block_ids[0]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["block_id"] == seeded.block_ids[0]
    assert body["title"].startswith("Page 1 Block 1")
    assert body["messages"] == []
    assert body["page_num"] == 1


@pytest.mark.asyncio
async def test_create_thread_with_custom_title(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.post("/threads", json={"block_id": seeded.block_ids[0], "title": "내 메모"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "내 메모"


@pytest.mark.asyncio
async def test_create_thread_404_for_unknown_block(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.post("/threads", json={"block_id": 9999})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "block not found"


@pytest.mark.asyncio
async def test_list_threads_filter_by_doc_id(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        a = await seed_minimal_document(session, tmp_dir=tmp_path, filename="a.pdf")
        b = await seed_minimal_document(session, tmp_dir=tmp_path, filename="b.pdf")
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        client.post("/threads", json={"block_id": a.block_ids[0]})
        client.post("/threads", json={"block_id": a.block_ids[1]})
        client.post("/threads", json={"block_id": b.block_ids[0]})

        resp_all = client.get("/threads")
        assert resp_all.status_code == 200
        assert len(resp_all.json()) == 3

        resp_a = client.get(f"/threads?doc_id={a.doc_id}")
        assert len(resp_a.json()) == 2

        resp_b = client.get(f"/threads?doc_id={b.doc_id}")
        assert len(resp_b.json()) == 1


@pytest.mark.asyncio
async def test_get_thread_returns_404_when_missing(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/threads/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_thread_includes_block_and_messages_in_order(
    api_db_path: Path, tmp_path: Path
) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        thread = client.post("/threads", json={"block_id": seeded.block_ids[0]}).json()
        # explain → 2 messages
        client.post(f"/threads/{thread['id']}/explain")
        # post a follow-up → 2 more messages
        client.post(
            f"/threads/{thread['id']}/messages",
            json={"content": "더 자세히"},
        )
        resp = client.get(f"/threads/{thread['id']}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["block"]["block_local_id"] == "p1_b001"
    assert body["block"]["has_thread"] is True
    assert body["page_num"] == 1
    msgs = body["messages"]
    assert len(msgs) == 4
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    # ids should be monotonically increasing
    assert [m["id"] for m in msgs] == sorted(m["id"] for m in msgs)


@pytest.mark.asyncio
async def test_get_thread_messages_route_returns_history_in_order(
    api_db_path: Path, tmp_path: Path
) -> None:
    """``GET /threads/{id}/messages`` is a dedicated history endpoint."""
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        thread = client.post("/threads", json={"block_id": seeded.block_ids[0]}).json()
        client.post(f"/threads/{thread['id']}/explain")
        client.post(
            f"/threads/{thread['id']}/messages",
            json={"content": "follow-up"},
        )

        resp = client.get(f"/threads/{thread['id']}/messages")
        assert resp.status_code == 200
        msgs = resp.json()

    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["id"] for m in msgs] == sorted(m["id"] for m in msgs)


@pytest.mark.asyncio
async def test_get_thread_messages_route_404_when_thread_missing(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/threads/9999/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_thread_summary_includes_message_count(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        thread = client.post("/threads", json={"block_id": seeded.block_ids[0]}).json()
        client.post(f"/threads/{thread['id']}/explain")
        resp = client.get("/threads")
    body = resp.json()
    assert len(body) == 1
    assert body[0]["message_count"] == 2
