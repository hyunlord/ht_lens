"""Phase 8e-5 — `ht-lens repair-images` CLI (verify-cross R2 §4#1/#3/#4).

Locks command wiring, dry-run no-write, the reviewed-allowlist policy (a
captions-only seed repairs NO images), and controlled seed-parse failure."""

from __future__ import annotations

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
