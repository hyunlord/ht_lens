"""Phase 8e-7 — ingest-mineru-multi integration (merge → reuse ingest_mineru_output).

Locks the end-to-end split-merge ingest: N part outputs → ONE document via the
existing pipeline; merged page_idx monotonic, chunk count = Σ parts, images
served, and single-part = plain ingest-mineru equivalence (regression)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ht_lens.cli import app

from ._api_helpers import make_test_client

runner = CliRunner()


def _tiny_pdf(path: Path, pages: int) -> None:
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=576, height=648)
    doc.save(str(path))
    doc.close()


def _part(root: Path, name: str, items: list[dict], images: dict[str, bytes], pages: int) -> Path:
    """A synthetic MinerU part output dir (content_list + images/ + origin.pdf)."""
    d = root / name
    (d / "images").mkdir(parents=True)
    (d / f"{name}_content_list.json").write_text(json.dumps(items))
    for base, data in images.items():
        (d / "images" / base).write_bytes(data)
    _tiny_pdf(d / f"{name}_origin.pdf", pages)
    return d


_JPG = b"\xff\xd8\xff\xe0jpgdata"


def _env(monkeypatch: pytest.MonkeyPatch, tmp: Path) -> None:
    monkeypatch.setenv("HT_LENS_MINERU_OUT_DIR", str(tmp / "mineru_out"))
    monkeypatch.setenv("HT_LENS_EXTRACTS_V2_DIR", str(tmp / "ev2"))


def test_ingest_multi_merges_two_parts_into_one_doc(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch, tmp_path)
    p0 = _part(
        tmp_path,
        "p0",
        [
            {"type": "text", "text": "alpha", "page_idx": 0},
            {
                "type": "image",
                "img_path": "images/f.jpg",
                "image_caption": ["Fig 1"],
                "page_idx": 1,
            },
        ],
        {"f.jpg": _JPG},
        2,
    )
    p1 = _part(
        tmp_path,
        "p1",
        [
            {"type": "text", "text": "beta", "page_idx": 0},
            {
                "type": "image",
                "img_path": "images/f.jpg",
                "image_caption": ["Fig 2"],
                "page_idx": 1,
            },
        ],
        {"f.jpg": b"\xff\xd8\xff\xe0different"},  # SAME basename, different bytes
        2,
    )
    full = tmp_path / "book.pdf"
    _tiny_pdf(full, 4)
    res = runner.invoke(
        app,
        [
            "ingest-mineru-multi",
            str(p0),
            str(p1),
            "--filename",
            "book.pdf",
            "--source-pdf",
            str(full),
            "--db",
            str(api_db_path),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "merged 2 parts" in res.output

    with make_test_client(api_db_path) as client:
        # the merged doc is the only one in this fresh api_db
        data = client.get("/v2/documents/1/reflow").json()
        chunks = data["chunks"]
        pages = [c["page_idx"] for c in chunks]
        assert pages == sorted(pages)  # monotonic non-decreasing across the merge
        assert max(pages) == 3  # part1 page1 + offset2 (part0 page_count)
        assert len(chunks) == 4  # 2 text + 2 image = Σ parts
        imgs = [c for c in chunks if c["type"] == "image"]
        assert len(imgs) == 2
        for im in imgs:
            assert client.get(im["img_url"]).status_code == 200  # namespaced images served


def test_ingest_multi_single_part_equivalent(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One part → same result as a plain ingest (offset 0, no namespacing impact
    on counts): regression that the multi path doesn't distort single-doc ingest."""
    _env(monkeypatch, tmp_path)
    p0 = _part(
        tmp_path,
        "solo",
        [
            {"type": "text", "text": "a", "page_idx": 0},
            {"type": "text", "text": "b", "page_idx": 1},
        ],
        {},
        2,
    )
    full = tmp_path / "solo.pdf"
    _tiny_pdf(full, 2)
    res = runner.invoke(
        app,
        [
            "ingest-mineru-multi",
            str(p0),
            "--filename",
            "solo.pdf",
            "--source-pdf",
            str(full),
            "--db",
            str(api_db_path),
        ],
    )
    assert res.exit_code == 0, res.output
    with make_test_client(api_db_path) as client:
        chunks = client.get("/v2/documents/1/reflow").json()["chunks"]
    assert [c["page_idx"] for c in chunks] == [0, 1]  # offset 0, unchanged
    assert len(chunks) == 2


def test_ingest_multi_provenance_resolves_full_pdf_for_repair(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """challenge §5#1: after multi ingest, detect-repairs must resolve the FULL
    source PDF via the merged doc's markdown_path (not a part origin), so repair
    clips absolute pages. It succeeds (exit 0) instead of 'source PDF not found'."""
    _env(monkeypatch, tmp_path)
    p0 = _part(tmp_path, "p0", [{"type": "text", "text": "a", "page_idx": 0}], {}, 2)
    p1 = _part(tmp_path, "p1", [{"type": "text", "text": "b", "page_idx": 0}], {}, 2)
    full = tmp_path / "book.pdf"
    _tiny_pdf(full, 4)
    r1 = runner.invoke(
        app,
        [
            "ingest-mineru-multi",
            str(p0),
            str(p1),
            "--filename",
            "book.pdf",
            "--source-pdf",
            str(full),
            "--db",
            str(api_db_path),
        ],
    )
    assert r1.exit_code == 0, r1.output
    # detect-repairs autodiscovers *_origin.pdf from the merged doc's markdown dir
    r2 = runner.invoke(app, ["detect-repairs", "--doc-id", "1", "--db", str(api_db_path)])
    assert r2.exit_code == 0, r2.output  # full origin resolved, no "source PDF not found"


def test_ingest_multi_all_chrome_rejected(
    api_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """challenge §5#3: parts may be individually empty, but an all-chrome merged
    document (zero content chunks) is rejected by the reused ingest pipeline."""
    _env(monkeypatch, tmp_path)
    p0 = _part(tmp_path, "p0", [{"type": "page_number", "text": "1", "page_idx": 0}], {}, 2)
    p1 = _part(tmp_path, "p1", [{"type": "header", "text": "h", "page_idx": 0}], {}, 2)
    full = tmp_path / "book.pdf"
    _tiny_pdf(full, 4)
    res = runner.invoke(
        app,
        [
            "ingest-mineru-multi",
            str(p0),
            str(p1),
            "--filename",
            "book.pdf",
            "--source-pdf",
            str(full),
            "--db",
            str(api_db_path),
        ],
    )
    assert res.exit_code != 0  # zero-chunk merged doc rejected
