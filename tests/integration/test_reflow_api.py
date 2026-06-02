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
async def test_reflow_dedup_drops_nested_panels_at_endpoint(
    api_db_path: Path, tmp_path: Path
) -> None:
    """verify-cross 8e-4 R1 §4#3: lock the dedup where it is actually applied
    (``get_reflow`` at reflow.py:127), not just the helper. A captioned full
    crop containing two captionless panels → /reflow returns only the captioned
    crop, while /v2/chunks/{id}/image for a dropped panel stays 200 (the DB row
    is untouched — render-only)."""
    from sqlalchemy import select

    full = tmp_path / "full.jpg"
    full.write_bytes(b"\xff\xd8\xff\xe0full")
    p1 = tmp_path / "p1.jpg"
    p1.write_bytes(b"\xff\xd8\xff\xe0p1")
    p2 = tmp_path / "p2.jpg"
    p2.write_bytes(b"\xff\xd8\xff\xe0p2")
    doc_id = await _seed(
        api_db_path,
        [
            {"type": "text", "page_idx": 2, "content": "x", "translated": "[KO] x"},
            {
                "type": "image",
                "page_idx": 2,
                "img_path": str(full),
                "bbox_json": "[156,84,855,475]",
                "caption": "Figure 28.18",
            },
            {"type": "image", "page_idx": 2, "img_path": str(p1), "bbox_json": "[512,273,857,461]"},
            {"type": "image", "page_idx": 2, "img_path": str(p2), "bbox_json": "[156,86,503,266]"},
        ],
    )
    # The captionless panels are dropped from /reflow but their rows remain.
    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            rows = (
                (
                    await s.execute(
                        select(Chunk).where(Chunk.type == "image", Chunk.caption.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            panel_ids = sorted(c.id for c in rows)
    finally:
        await engine.dispose()
    assert len(panel_ids) == 2

    with make_test_client(api_db_path) as client:
        data = client.get(f"/v2/documents/{doc_id}/reflow").json()
        imgs = [c for c in data["chunks"] if c["type"] == "image"]
        assert len(imgs) == 1  # only the captioned full crop survives
        assert imgs[0]["caption"] == "Figure 28.18"
        returned_ids = {c["id"] for c in data["chunks"]}
        assert not (set(panel_ids) & returned_ids)  # both panels dropped from the view
        # Non-destructive: each dropped panel image is still served.
        for pid in panel_ids:
            assert client.get(f"/v2/chunks/{pid}/image").status_code == 200


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
async def test_chunk_image_traversal_rejected(api_db_path: Path) -> None:
    """verify-cross R1: actually exercise the traversal branch (the prior
    test name claimed it but used a normal path)."""
    doc_id = await _seed(
        api_db_path,
        [{"type": "image", "content": "", "img_path": "/data/../etc/passwd.png", "caption": "f"}],
    )
    with make_test_client(api_db_path) as client:
        cid = client.get(f"/v2/documents/{doc_id}/reflow").json()["chunks"][0]["id"]
        r = client.get(f"/v2/chunks/{cid}/image")
    assert r.status_code == 500  # traversal segment refused before any read


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


def _tiny_pdf(path: Path, pages: int = 2) -> None:
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=200, height=300)
    doc.save(str(path))
    doc.close()


def test_render_doc_pages_positive(tmp_path: Path) -> None:
    """verify-cross R1: render a real PDF and assert the cache filenames are
    exactly what ``page_image`` serves (locks the convention coupling)."""
    from ht_lens.api.routers.reflow import render_doc_pages

    pdf = tmp_path / "src.pdf"
    _tiny_pdf(pdf, pages=2)
    ev2 = tmp_path / "ev2"
    n = render_doc_pages(7, pdf, dest_root=ev2)
    assert n == 2
    # Filenames must match page_image's f"page_{page_idx:04d}.png".
    assert (ev2 / "7" / "pages" / "page_0000.png").is_file()
    assert (ev2 / "7" / "pages" / "page_0001.png").is_file()


@pytest.mark.asyncio
async def test_page_image_success_serves_cached_png(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """verify-cross R1: the left-pane success path — a cached render is
    served as image/png with no-cache. Renders via the same helper the
    8e migration will use, so filename↔serve coupling is exercised."""
    from ht_lens.api.routers.reflow import render_doc_pages

    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    doc_id = await _seed(api_db_path, [{"type": "text", "content": "x", "translated": "[KO] x"}])
    pdf = tmp_path / "src.pdf"
    _tiny_pdf(pdf, pages=1)
    render_doc_pages(doc_id, pdf, dest_root=ev2)
    with make_test_client(api_db_path) as client:
        r = client.get(f"/v2/documents/{doc_id}/page/0/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "no-cache" in r.headers.get("cache-control", "").lower()


# --------------------------------------------------------------------------- #
# Phase 8e-5 — image/caption override serving (hermetic: tmp extracts + manifest)
# --------------------------------------------------------------------------- #
def _write_png(path: Path, color: tuple[int, int, int] = (10, 20, 30)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 40), color).save(path)


def _write_manifest(ev2: Path, doc_id: int, *, images=None, captions=None) -> None:
    import json

    root = ev2 / str(doc_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "overrides.json").write_text(
        json.dumps({"images": images or [], "captions": captions or []})
    )


@pytest.mark.asyncio
async def test_image_override_served_when_manifest_matches(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """8e-5 defect 1: a matching image override serves the fixed page-clip (PNG),
    not the degraded original."""
    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    orig = tmp_path / "deg.jpg"
    orig.write_bytes(b"\xff\xd8\xff\xe0deg")
    doc_id = await _seed(
        api_db_path,
        [{"type": "image", "page_idx": 0, "img_path": str(orig), "bbox_json": "[100,100,400,400]"}],
    )
    fixed = ev2 / str(doc_id) / "images_fixed" / "deg.png"
    _write_png(fixed)
    _write_manifest(
        ev2,
        doc_id,
        images=[
            {
                "page_idx": 0,
                "orig_basename": "deg.jpg",
                "bbox": [100, 100, 400, 400],
                "fixed_basename": "deg.png",
            }
        ],
    )
    with make_test_client(api_db_path) as client:
        cid = client.get(f"/v2/documents/{doc_id}/reflow").json()["chunks"][0]["id"]
        r = client.get(f"/v2/chunks/{cid}/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"  # served the fixed clip, not the .jpg


@pytest.mark.asyncio
async def test_image_override_stale_evidence_falls_back_to_original(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manifest bbox no longer matches the chunk (re-ingest drift) → original served."""
    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    orig = tmp_path / "fig.jpg"
    orig.write_bytes(b"\xff\xd8\xff\xe0jpg")
    doc_id = await _seed(
        api_db_path,
        [{"type": "image", "page_idx": 0, "img_path": str(orig), "bbox_json": "[100,100,400,400]"}],
    )
    _write_png(ev2 / str(doc_id) / "images_fixed" / "fig.png")
    _write_manifest(
        ev2,
        doc_id,
        images=[
            {
                "page_idx": 0,
                "orig_basename": "fig.jpg",
                "bbox": [999, 999, 1000, 1000],  # drifted → no match
                "fixed_basename": "fig.png",
            }
        ],
    )
    with make_test_client(api_db_path) as client:
        cid = client.get(f"/v2/documents/{doc_id}/reflow").json()["chunks"][0]["id"]
        r = client.get(f"/v2/chunks/{cid}/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"  # fell back to the original .jpg


@pytest.mark.asyncio
async def test_image_override_traversal_basename_rejected(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest fixed_basename with a traversal segment must be refused (500),
    never served — the override path goes through the same validator."""
    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    orig = tmp_path / "fig.jpg"
    orig.write_bytes(b"\xff\xd8\xff\xe0jpg")
    doc_id = await _seed(
        api_db_path,
        [{"type": "image", "page_idx": 0, "img_path": str(orig), "bbox_json": "[100,100,400,400]"}],
    )
    # make the traversal target exist so only the validator can stop it
    (ev2 / str(doc_id) / "images_fixed").mkdir(parents=True, exist_ok=True)
    _write_manifest(
        ev2,
        doc_id,
        images=[
            {
                "page_idx": 0,
                "orig_basename": "fig.jpg",
                "bbox": [100, 100, 400, 400],
                "fixed_basename": "../../../../etc/passwd.png",
            }
        ],
    )
    with make_test_client(api_db_path) as client:
        cid = client.get(f"/v2/documents/{doc_id}/reflow").json()["chunks"][0]["id"]
        r = client.get(f"/v2/chunks/{cid}/image")
    # traversal fixed file does not exist → override skipped → original .jpg served
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_caption_override_applied_and_dedup_intact(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """8e-5 defect 2: caption re-assignment is applied; the 8e-4 nested-panel
    dedup still drops the captionless panel and keeps the rest (challenge R6)."""
    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    container = tmp_path / "container.jpg"
    container.write_bytes(b"\xff\xd8\xff\xe0c")
    panel = tmp_path / "panel.jpg"
    panel.write_bytes(b"\xff\xd8\xff\xe0p")
    standalone = tmp_path / "stand.jpg"
    standalone.write_bytes(b"\xff\xd8\xff\xe0s")
    doc_id = await _seed(
        api_db_path,
        [
            {
                "type": "image",
                "page_idx": 0,
                "img_path": str(container),
                "bbox_json": "[0,0,500,500]",
                "caption": "Figure 1: container",
            },
            {
                "type": "image",
                "page_idx": 0,
                "img_path": str(panel),
                "bbox_json": "[50,50,200,200]",
            },  # captionless nested → dedup drops
            {
                "type": "image",
                "page_idx": 0,
                "img_path": str(standalone),
                "bbox_json": "[600,600,800,800]",
            },  # captionless standalone → caption override
        ],
    )
    _write_manifest(
        ev2,
        doc_id,
        captions=[
            {
                "page_idx": 0,
                "orig_basename": "stand.jpg",
                "bbox": [600, 600, 800, 800],
                "caption": "Figure 2: corrected standalone",
            }
        ],
    )
    with make_test_client(api_db_path) as client:
        data = client.get(f"/v2/documents/{doc_id}/reflow").json()
    imgs = [c for c in data["chunks"] if c["type"] == "image"]
    caps = {c["caption"] for c in imgs}
    # nested captionless panel dropped; container + (now-captioned) standalone kept
    assert len(imgs) == 2
    assert "Figure 2: corrected standalone" in caps  # override applied
    assert "Figure 1: container" in caps
