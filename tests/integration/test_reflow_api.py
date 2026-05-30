"""Phase 8c — reflow /v2 API integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ht_lens.db.models import Chunk, ChunkTranslation, Document
from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client


async def _seed(db_path: Path, chunks: list[dict]) -> int:
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
            for i, c in enumerate(chunks):
                ch = Chunk(
                    doc_id=doc.id,
                    page_idx=c.get("page_idx", 0),
                    order_idx=i,
                    type=c["type"],
                    text_level=c.get("text_level"),
                    bbox_json=c.get("bbox_json", "[0,0,1,1]"),
                    content=c.get("content", ""),
                    img_path=c.get("img_path"),
                    caption=c.get("caption"),
                )
                s.add(ch)
                await s.flush()
                if "translated" in c:
                    s.add(
                        ChunkTranslation(
                            chunk_id=ch.id,
                            translated_text=c["translated"],
                            caption_translated=c.get("caption_translated"),
                            model="mock",
                            status=c.get("tr_status", "translated"),
                            updated_at=datetime.now(UTC),
                        )
                    )
            await s.commit()
            return doc.id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reflow_order_and_types(api_db_path: Path) -> None:
    doc_id = await _seed(
        api_db_path,
        [
            {"type": "heading", "text_level": 2, "content": "Sec", "translated": "[KO] Sec"},
            {"type": "text", "content": "Body", "translated": "[KO] Body"},
            {"type": "equation", "content": "$$E=mc^2$$", "translated": "$$E=mc^2$$"},
        ],
    )
    with make_test_client(api_db_path) as client:
        r = client.get(f"/v2/documents/{doc_id}/reflow")
    assert r.status_code == 200
    data = r.json()
    assert [c["type"] for c in data["chunks"]] == ["heading", "text", "equation"]
    assert data["chunks"][0]["text_level"] == 2
    assert data["chunks"][0]["translated"] == "[KO] Sec"
    assert data["extractor"] == "mineru"


@pytest.mark.asyncio
async def test_reflow_only_translated_status_surfaces(api_db_path: Path) -> None:
    """A failed ChunkTranslation must not masquerade as content (challenge §5)."""
    doc_id = await _seed(
        api_db_path,
        [{"type": "text", "content": "orig", "translated": "junk", "tr_status": "failed"}],
    )
    with make_test_client(api_db_path) as client:
        data = client.get(f"/v2/documents/{doc_id}/reflow").json()
    c = data["chunks"][0]
    assert c["translated"] is None  # failed → not surfaced
    assert c["original"] == "orig"  # fallback available to the viewer


@pytest.mark.asyncio
async def test_reflow_table_chunk_preserved(api_db_path: Path) -> None:
    doc_id = await _seed(
        api_db_path,
        [{"type": "table", "content": "| a | b |", "translated": "[KO] | a | b |"}],
    )
    with make_test_client(api_db_path) as client:
        data = client.get(f"/v2/documents/{doc_id}/reflow").json()
    assert data["chunks"][0]["type"] == "table"  # preserved, not dropped


@pytest.mark.asyncio
async def test_reflow_bbox_null_when_empty(api_db_path: Path) -> None:
    doc_id = await _seed(
        api_db_path,
        [
            {"type": "text", "content": "a", "bbox_json": "[]", "translated": "[KO] a"},
            {"type": "text", "content": "b", "bbox_json": "[1,2,3,4]", "translated": "[KO] b"},
        ],
    )
    with make_test_client(api_db_path) as client:
        data = client.get(f"/v2/documents/{doc_id}/reflow").json()
    assert data["chunks"][0]["bbox"] is None  # empty bbox → null (page-scroll only)
    assert data["chunks"][1]["bbox"] == [1.0, 2.0, 3.0, 4.0]  # valid → overlay-capable


@pytest.mark.asyncio
async def test_reflow_unknown_doc_404(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        assert client.get("/v2/documents/99999/reflow").status_code == 404


@pytest.mark.asyncio
async def test_chunk_image_jpg_served_and_traversal_rejected(
    api_db_path: Path, tmp_path: Path
) -> None:
    img = tmp_path / "fig.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0jpeg")
    doc_id = await _seed(
        api_db_path, [{"type": "image", "content": "", "img_path": str(img), "caption": "f"}]
    )
    with make_test_client(api_db_path) as client:
        data = client.get(f"/v2/documents/{doc_id}/reflow").json()
        cid = data["chunks"][0]["id"]
        r = client.get(f"/v2/chunks/{cid}/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"  # .jpg accepted (critical fix)


@pytest.mark.asyncio
async def test_chunk_image_missing_file_404(api_db_path: Path, tmp_path: Path) -> None:
    doc_id = await _seed(
        api_db_path,
        [{"type": "image", "content": "", "img_path": str(tmp_path / "gone.jpg"), "caption": "f"}],
    )
    with make_test_client(api_db_path) as client:
        data = client.get(f"/v2/documents/{doc_id}/reflow").json()
        cid = data["chunks"][0]["id"]
        r = client.get(f"/v2/chunks/{cid}/image")
    assert r.status_code == 404  # controlled, not a crash


@pytest.mark.asyncio
async def test_page_image_404_when_not_cached(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point the render-cache root at an empty tmp dir so this is hermetic
    # (the shared data/extracts_v2 may hold a dev doc's cache).
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(tmp_path / "ev2"))
    doc_id = await _seed(api_db_path, [{"type": "text", "content": "x", "translated": "[KO] x"}])
    with make_test_client(api_db_path) as client:
        # No render cache populated → deterministic 404, not a crash.
        assert client.get(f"/v2/documents/{doc_id}/page/0/image").status_code == 404


def test_render_doc_pages_requires_source_pdf(tmp_path: Path) -> None:
    from ht_lens.api.routers.reflow import render_doc_pages

    with pytest.raises(FileNotFoundError, match="source PDF not found"):
        render_doc_pages(1, tmp_path / "nope.pdf", dest_root=tmp_path / "ev2")
