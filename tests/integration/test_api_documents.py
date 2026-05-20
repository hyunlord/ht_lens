"""Phase 3 — /documents endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client, seed_minimal_document


@pytest.mark.asyncio
async def test_list_documents_returns_seeded_doc(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, num_pages=2)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get("/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == seeded.doc_id
    assert body[0]["filename"] == "sample.pdf"
    assert body[0]["num_pages"] == 2


@pytest.mark.asyncio
async def test_get_document_returns_404_when_missing(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/documents/999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "document not found"


@pytest.mark.asyncio
async def test_get_document_returns_seeded_doc(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        seeded = await seed_minimal_document(session, tmp_dir=tmp_path, num_pages=3)
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get(f"/documents/{seeded.doc_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == seeded.doc_id
    assert body["num_pages"] == 3
    assert body["status"] == "translated"


@pytest.mark.asyncio
async def test_list_documents_status_filter(api_db_path: Path, tmp_path: Path) -> None:
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        await seed_minimal_document(session, tmp_dir=tmp_path, filename="a.pdf")
        await seed_minimal_document(
            session, tmp_dir=tmp_path, filename="b.pdf", with_translations=False
        )
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        resp = client.get("/documents?status=translated")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["filename"] == "a.pdf"

        resp2 = client.get("/documents?status=ingested")
        assert len(resp2.json()) == 1
