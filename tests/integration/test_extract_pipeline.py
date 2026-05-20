"""End-to-end extract pipeline against the three sample PDFs."""

from __future__ import annotations

import json
import re
from math import ceil
from pathlib import Path

import pytest
from PIL import Image

from ht_lens.extract.pipeline import extract_pdf

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

EXPECTED_LANG = {
    "sample_en.pdf": "en",
    "sample_ko.pdf": "ko",
    "sample_mixed.pdf": "mixed",
}

_BLOCK_ID = re.compile(r"^p\d+_b\d{3}$")


def test_fixture_pdfs_exist_and_are_nonempty() -> None:
    for name in EXPECTED_LANG:
        p = FIXTURES / name
        assert p.exists(), f"missing fixture: {p}"
        assert p.stat().st_size > 0, f"empty fixture: {p}"


@pytest.fixture(scope="module")
def extracted_en(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("en")
    extract_pdf(FIXTURES / "sample_en.pdf", out)
    return out


@pytest.fixture(scope="module")
def extracted_ko(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("ko")
    extract_pdf(FIXTURES / "sample_ko.pdf", out)
    return out


@pytest.fixture(scope="module")
def extracted_mixed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("mixed")
    extract_pdf(FIXTURES / "sample_mixed.pdf", out)
    return out


@pytest.mark.parametrize(
    "sample_name,extracted_fixture",
    [
        ("sample_en.pdf", "extracted_en"),
        ("sample_ko.pdf", "extracted_ko"),
        ("sample_mixed.pdf", "extracted_mixed"),
    ],
)
def test_doc_meta_has_expected_lang(
    sample_name: str, extracted_fixture: str, request: pytest.FixtureRequest
) -> None:
    out: Path = request.getfixturevalue(extracted_fixture)
    meta = json.loads((out / "doc_meta.json").read_text())
    assert meta["filename"] == sample_name
    assert meta["num_pages"] > 0
    assert meta["lang_guess"] == EXPECTED_LANG[sample_name]
    assert len(meta["src_pdf_sha256"]) == 64
    assert meta["extractor_version"]


def _iter_page_jsons(out: Path) -> list[Path]:
    return sorted((out / "pages").glob("page_*.json"))


def _iter_page_pngs(out: Path) -> list[Path]:
    return sorted((out / "pages").glob("page_*.png"))


@pytest.mark.parametrize(
    "extracted_fixture",
    ["extracted_en", "extracted_ko", "extracted_mixed"],
)
def test_every_page_has_png_and_json(
    extracted_fixture: str, request: pytest.FixtureRequest
) -> None:
    out: Path = request.getfixturevalue(extracted_fixture)
    pngs = _iter_page_pngs(out)
    jsons = _iter_page_jsons(out)
    assert len(pngs) == len(jsons)
    assert len(pngs) > 0


@pytest.mark.parametrize(
    "extracted_fixture",
    ["extracted_en", "extracted_ko", "extracted_mixed"],
)
def test_page_json_schema_and_id_pattern(
    extracted_fixture: str, request: pytest.FixtureRequest
) -> None:
    out: Path = request.getfixturevalue(extracted_fixture)
    total_blocks = 0
    for jpath in _iter_page_jsons(out):
        doc = json.loads(jpath.read_text())
        assert doc["unit"] == "pt"
        for key in ("page_num", "width", "height", "rotation", "render", "blocks"):
            assert key in doc, f"missing field {key} in {jpath.name}"
        render = doc["render"]
        for key in ("dpi", "pixel_width", "pixel_height", "scale"):
            assert key in render
        for blk in doc["blocks"]:
            assert _BLOCK_ID.match(blk["id"]), blk["id"]
            assert blk["type"] in ("text", "image", "header")
            assert len(blk["bbox"]) == 4
            assert blk["order"] >= 1
        total_blocks += len(doc["blocks"])
    assert total_blocks > 0, "document must have at least one block somewhere"


@pytest.mark.parametrize(
    "extracted_fixture",
    ["extracted_en", "extracted_ko", "extracted_mixed"],
)
def test_page_json_records_coordinate_space_and_render_scale(
    extracted_fixture: str, request: pytest.FixtureRequest
) -> None:
    out: Path = request.getfixturevalue(extracted_fixture)
    for jpath in _iter_page_jsons(out):
        doc = json.loads(jpath.read_text())
        render = doc["render"]
        assert render["dpi"] == 200
        assert abs(render["scale"] - 200 / 72.0) < 1e-3
        if doc["rotation"] in (90, 270):
            expected_w = ceil(doc["height"] * render["scale"])
            expected_h = ceil(doc["width"] * render["scale"])
        else:
            expected_w = ceil(doc["width"] * render["scale"])
            expected_h = ceil(doc["height"] * render["scale"])
        # PyMuPDF may produce ±1 pixel rounding differences vs ceil(width*scale).
        assert abs(render["pixel_width"] - expected_w) <= 1
        assert abs(render["pixel_height"] - expected_h) <= 1

        png_path = jpath.with_suffix(".png")
        with Image.open(png_path) as img:
            # Stored values are now measured from the rendered PNG, so they
            # must match exactly.
            assert img.width == render["pixel_width"]
            assert img.height == render["pixel_height"]
