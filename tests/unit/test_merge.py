"""Phase 8e-7 — split-output merge unit tests.

Locks the offset/boundary/namespace/validation core (challenge R2-R6): page_idx
offset by cumulative source-PDF page count, out-of-bounds reject, per-part image
namespacing (no dup-basename overwrite), empty-part offset, full-PDF provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ht_lens.errors import IngestError
from ht_lens.ingest_mineru.merge import (
    MergePart,
    build_merged_output,
    offset_items,
)


# --------------------------------------------------------------------------- #
# offset_items (pure)
# --------------------------------------------------------------------------- #
def test_offset_items_applies_page_offset_and_namespaces() -> None:
    items = [
        {"type": "text", "text": "a", "page_idx": 0},
        {"type": "image", "img_path": "images/fig1.jpg", "page_idx": 1},
    ]
    out, renames = offset_items(items, page_offset=10, part_index=2, page_count=3)
    assert [i["page_idx"] for i in out] == [10, 11]
    assert out[1]["img_path"] == "images/part002__fig1.jpg"
    assert renames == [("fig1.jpg", "part002__fig1.jpg")]
    # input not mutated
    assert items[1]["img_path"] == "images/fig1.jpg"


def test_offset_items_rejects_out_of_bounds_page_idx() -> None:
    with pytest.raises(IngestError, match="out of bounds"):
        offset_items([{"page_idx": 3}], page_offset=0, part_index=0, page_count=3)
    with pytest.raises(IngestError, match="out of bounds"):
        offset_items([{"page_idx": -1}], page_offset=0, part_index=0, page_count=3)


def test_offset_items_rejects_non_int_page_idx() -> None:
    with pytest.raises(IngestError, match="non-int page_idx"):
        offset_items([{"page_idx": "2"}], page_offset=0, part_index=0, page_count=3)
    with pytest.raises(IngestError, match="non-int page_idx"):
        offset_items([{"page_idx": True}], page_offset=0, part_index=0, page_count=3)  # bool != int


# --------------------------------------------------------------------------- #
# build_merged_output
# --------------------------------------------------------------------------- #
def _tiny_pdf(path: Path, pages: int) -> None:
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=576, height=648)
    doc.save(str(path))
    doc.close()


def _part(
    tmp: Path, name: str, items: list[dict], images: dict[str, bytes], pages: int
) -> MergePart:
    d = tmp / name
    (d / "images").mkdir(parents=True)
    cl = d / f"{name}_content_list.json"
    cl.write_text(json.dumps(items))
    for base, data in images.items():
        (d / "images" / base).write_bytes(data)
    origin = d / f"{name}_origin.pdf"
    _tiny_pdf(origin, pages)
    return MergePart(cl, d / "images", origin, pages)


def test_build_merged_output_boundary_continuity(tmp_path: Path) -> None:
    # part1 = 3 pages, last content on page 2; part2 = 2 pages, first on page 0.
    p1 = _part(tmp_path, "p1", [{"type": "text", "text": "end", "page_idx": 2}], {}, 3)
    p2 = _part(tmp_path, "p2", [{"type": "text", "text": "start", "page_idx": 0}], {}, 2)
    src = tmp_path / "full.pdf"
    _tiny_pdf(src, 5)
    merged = build_merged_output(
        [p1, p2], dest_dir=tmp_path / "m", source_pdf=src, filename_stem="full"
    )
    items = json.loads(merged.content_list_path.read_text())
    pages = [i["page_idx"] for i in items]
    assert pages == [2, 3]  # part2 page0 → 0+3(part1 count) = 3, contiguous after 2
    assert pages == sorted(pages)  # monotonic non-decreasing


def test_build_merged_output_namespaces_dup_basename(tmp_path: Path) -> None:
    # both parts have images/fig1.jpg with DIFFERENT bytes → must not overwrite.
    p1 = _part(
        tmp_path,
        "p1",
        [{"type": "image", "img_path": "images/fig1.jpg", "page_idx": 0}],
        {"fig1.jpg": b"AAAA"},
        1,
    )
    p2 = _part(
        tmp_path,
        "p2",
        [{"type": "image", "img_path": "images/fig1.jpg", "page_idx": 0}],
        {"fig1.jpg": b"BBBB"},
        1,
    )
    src = tmp_path / "full.pdf"
    _tiny_pdf(src, 2)
    merged = build_merged_output(
        [p1, p2], dest_dir=tmp_path / "m", source_pdf=src, filename_stem="full"
    )
    a = merged.images_dir / "part000__fig1.jpg"
    b = merged.images_dir / "part001__fig1.jpg"
    assert a.read_bytes() == b"AAAA" and b.read_bytes() == b"BBBB"  # distinct, no overwrite
    items = json.loads(merged.content_list_path.read_text())
    assert {i["img_path"] for i in items} == {
        "images/part000__fig1.jpg",
        "images/part001__fig1.jpg",
    }


def test_build_merged_output_empty_part_keeps_offset(tmp_path: Path) -> None:
    # part1 has page_count 3 but ZERO content items (blank/chrome) — part2 still
    # offsets by 3 (offset from source page count, not chunk count).
    p1 = _part(tmp_path, "p1", [], {}, 3)
    p2 = _part(tmp_path, "p2", [{"type": "text", "text": "x", "page_idx": 1}], {}, 2)
    src = tmp_path / "full.pdf"
    _tiny_pdf(src, 5)
    merged = build_merged_output(
        [p1, p2], dest_dir=tmp_path / "m", source_pdf=src, filename_stem="full"
    )
    items = json.loads(merged.content_list_path.read_text())
    assert [i["page_idx"] for i in items] == [4]  # part2 page1 + offset3 = 4


def test_build_merged_output_provenance_is_full_pdf(tmp_path: Path) -> None:
    p1 = _part(tmp_path, "p1", [{"type": "text", "text": "a", "page_idx": 0}], {}, 1)
    src = tmp_path / "full.pdf"
    _tiny_pdf(src, 7)  # full book has 7 pages
    merged = build_merged_output(
        [p1], dest_dir=tmp_path / "m", source_pdf=src, filename_stem="full"
    )
    import fitz

    origin = merged.content_list_path.parent / "full_origin.pdf"
    assert origin.is_file()
    doc = fitz.open(str(origin))
    try:
        assert doc.page_count == 7  # provenance = FULL pdf (not the 1-page part)
    finally:
        doc.close()
    assert merged.markdown_path.is_file()
