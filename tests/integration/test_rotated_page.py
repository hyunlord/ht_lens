"""Rotated page: rendered PNG matches the rotated page geometry."""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # type: ignore[import-untyped]
from PIL import Image

from ht_lens.extract.pipeline import extract_pdf


def _make_rotated_pdf(path: Path, rotation: int) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Rotated body text for langdetect padding. " * 6)
    page.set_rotation(rotation)
    doc.save(str(path))
    doc.close()


def test_rotated_page_bbox_matches_rendered_png_dimensions(tmp_path: Path) -> None:
    pdf = tmp_path / "rot.pdf"
    _make_rotated_pdf(pdf, rotation=90)
    out = tmp_path / "out"
    extract_pdf(pdf, out)

    page_json = json.loads((out / "pages" / "page_0001.json").read_text())
    assert page_json["rotation"] == 90

    with Image.open(out / "pages" / "page_0001.png") as img:
        assert abs(img.width - page_json["render"]["pixel_width"]) <= 1
        assert abs(img.height - page_json["render"]["pixel_height"]) <= 1
        # 90° rotation turns a US-letter portrait page into a landscape PNG.
        assert img.width > img.height
