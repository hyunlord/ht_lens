"""Phase 8e-5 — `ht-lens repair-images` CLI (verify-cross R2 §4#1/#3/#4).

Locks command wiring, dry-run no-write, the reviewed-allowlist policy (a
captions-only seed repairs NO images), and controlled seed-parse failure."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ht_lens.cli import app
from ht_lens.db.models import Chunk, Document
from ht_lens.db.session import make_engine, make_session_factory

runner = CliRunner()


def _origin_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=576, height=648)
    page.draw_rect(fitz.Rect(50, 50, 300, 300), fill=(0.1, 0.1, 0.1))
    doc.save(str(path))
    doc.close()


def _black_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (60, 60), (0, 0, 0)).save(path)


async def _seed_doc(db_path: Path, *, md_path: str, img_path: str) -> int:
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
                markdown_path=md_path,
            )
            s.add(doc)
            await s.flush()
            s.add(
                Chunk(
                    doc_id=doc.id,
                    page_idx=0,
                    order_idx=0,
                    type="image",
                    bbox_json="[100,100,500,500]",
                    content="",
                    img_path=img_path,
                )
            )
            await s.commit()
            return doc.id
    finally:
        await engine.dispose()


def test_repair_cli_invalid_seed_exits_2(api_db_path: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json ")
    res = runner.invoke(
        app,
        ["repair-images", "--doc-id", "1", "--seed", str(bad), "--db", str(api_db_path)],
    )
    assert res.exit_code == 2
    assert "invalid seed" in res.output


def test_repair_cli_dry_run_no_write(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    auto = tmp_path / "auto"
    auto.mkdir()
    _origin_pdf(auto / "doc_origin.pdf")
    img = tmp_path / "deg.jpg"
    _black_png(img)
    doc_id = asyncio.run(_seed_doc(api_db_path, md_path=str(auto / "x.md"), img_path=str(img)))
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"image_allowlist": ["deg.jpg"], "captions": []}))
    res = runner.invoke(
        app,
        ["repair-images", "--doc-id", str(doc_id), "--seed", str(seed), "--db", str(api_db_path)],
    )
    assert res.exit_code == 0, res.output
    assert "dry-run" in res.output and "detected=1" in res.output
    assert not (ev2 / str(doc_id) / "overrides.json").exists()  # dry-run writes nothing


def test_repair_cli_captions_only_seed_repairs_no_images(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewed-allowlist policy: an empty/absent image_allowlist must repair
    zero images even with --apply (no unreviewed clip-render)."""
    import asyncio

    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    auto = tmp_path / "auto"
    auto.mkdir()
    _origin_pdf(auto / "doc_origin.pdf")
    img = tmp_path / "deg.jpg"
    _black_png(img)
    doc_id = asyncio.run(_seed_doc(api_db_path, md_path=str(auto / "x.md"), img_path=str(img)))
    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps(
            {
                "captions": [
                    {
                        "page_idx": 0,
                        "orig_basename": "deg.jpg",
                        "bbox": [100, 100, 500, 500],
                        "caption": "Figure 1",
                    }
                ]
            }
        )
    )
    res = runner.invoke(
        app,
        [
            "repair-images",
            "--doc-id",
            str(doc_id),
            "--seed",
            str(seed),
            "--apply",
            "--db",
            str(api_db_path),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "written=0" in res.output  # detected dark image NOT repaired (not allowlisted)
    manifest = json.loads((ev2 / str(doc_id) / "overrides.json").read_text())
    assert manifest["images"] == [] and len(manifest["captions"]) == 1
    assert not (ev2 / str(doc_id) / "images_fixed").exists()


# --------------------------------------------------------------------------- #
# Phase 8e-6 — detect-repairs (read-only audit)
# --------------------------------------------------------------------------- #
async def _seed_doc_images(db_path: Path, *, md_path: str | None, images: list[dict]) -> int:
    """images: list of {page_idx, order_idx, img_path, bbox_json, caption}."""
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    try:
        async with factory() as s:
            doc = Document(
                filename="book.pdf",
                src_lang="en",
                tgt_lang="ko",
                status="translated",
                created_at=datetime.now(UTC),
                extractor="mineru",
                markdown_path=md_path,
            )
            s.add(doc)
            await s.flush()
            for im in images:
                s.add(
                    Chunk(
                        doc_id=doc.id,
                        page_idx=im["page_idx"],
                        order_idx=im["order_idx"],
                        type="image",
                        bbox_json=im.get("bbox_json", "[100,100,500,500]"),
                        content="",
                        img_path=im["img_path"],
                        caption=im.get("caption"),
                    )
                )
            await s.commit()
            return doc.id
    finally:
        await engine.dispose()


def test_detect_repairs_missing_origin_pdf_exits_2(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """verify-cross R1/R2: no source PDF (markdown_path None, no --pdf) must fail
    loudly, not emit an empty report."""
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(tmp_path / "ev2"))
    img = tmp_path / "x.jpg"
    _black_png(img)
    doc_id = asyncio.run(
        _seed_doc_images(
            api_db_path,
            md_path=None,
            images=[{"page_idx": 0, "order_idx": 0, "img_path": str(img)}],
        )
    )
    res = runner.invoke(app, ["detect-repairs", "--doc-id", str(doc_id), "--db", str(api_db_path)])
    assert res.exit_code != 0
    assert "source PDF not found" in res.output


def test_detect_repairs_reports_degraded_and_caption_mispair(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    auto = tmp_path / "auto"
    auto.mkdir()
    _origin_pdf(auto / "book_origin.pdf")
    deg = tmp_path / "deg.jpg"
    _black_png(deg)  # degraded (black)
    from PIL import Image

    ok1 = tmp_path / "ok1.jpg"
    Image.new("RGB", (60, 60), (255, 255, 255)).save(ok1)
    ok2 = tmp_path / "ok2.jpg"
    Image.new("RGB", (60, 60), (240, 240, 240)).save(ok2)
    doc_id = asyncio.run(
        _seed_doc_images(
            api_db_path,
            md_path=str(auto / "x.md"),
            images=[
                {"page_idx": 0, "order_idx": 0, "img_path": str(deg)},  # degraded
                # page 1: captionless + captioned (caption mispair)
                {"page_idx": 1, "order_idx": 1, "img_path": str(ok1)},  # captionless
                {
                    "page_idx": 1,
                    "order_idx": 2,
                    "img_path": str(ok2),
                    "caption": "(b) Foo Figure 9.1",
                },
            ],
        )
    )
    out = tmp_path / "draft.json"
    res = runner.invoke(
        app,
        ["detect-repairs", "--doc-id", str(doc_id), "--db", str(api_db_path), "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    draft = json.loads(out.read_text())
    assert draft["image_allowlist"] == ["deg.jpg"]  # only the degraded image
    assert "sha256" in draft["origin_pdf"]
    pages = [p["page_idx"] for p in draft["_caption_mispair_candidates"]]
    assert pages == [1]  # captionless+captioned page flagged
    # previews written under repair_preview, NOT served (no overrides.json)
    assert (ev2 / str(doc_id) / "repair_preview").is_dir()
    assert not (ev2 / str(doc_id) / "overrides.json").exists()


def test_detect_repairs_draft_not_served_by_reflow(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The draft seed + previews must not affect serving (only overrides.json
    does). chunk image still serves the original."""
    ev2 = tmp_path / "ev2"
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(ev2))
    auto = tmp_path / "auto"
    auto.mkdir()
    _origin_pdf(auto / "book_origin.pdf")
    deg = tmp_path / "deg.jpg"
    _black_png(deg)
    doc_id = asyncio.run(
        _seed_doc_images(
            api_db_path,
            md_path=str(auto / "x.md"),
            images=[{"page_idx": 0, "order_idx": 0, "img_path": str(deg)}],
        )
    )
    res = runner.invoke(app, ["detect-repairs", "--doc-id", str(doc_id), "--db", str(api_db_path)])
    assert res.exit_code == 0, res.output
    # no overrides.json → chunk_image serves the original degraded jpg
    from ._api_helpers import make_test_client

    with make_test_client(api_db_path) as client:
        cid = client.get(f"/v2/documents/{doc_id}/reflow").json()["chunks"][0]["id"]
        r = client.get(f"/v2/chunks/{cid}/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
