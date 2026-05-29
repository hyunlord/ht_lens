"""Phase 8a — MinerU content_list parser unit tests.

Locks the type mapping, chrome filter, malformed-field behavior, and the
load-bearing distinction that ``type=header`` is running chrome while
section headings are ``type=text`` + ``text_level`` (challenge §2.3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ht_lens.ingest_mineru.content_list import (
    CHROME_TYPES,
    ContentListError,
    parse_content_list,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "mineru" / "content_list_sample.json"


@pytest.fixture
def items() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_chrome_types_dropped(items: list[dict]) -> None:
    chunks = parse_content_list(items)
    # The fixture has 4 chrome items (header, page_number, page_footnote, footer).
    chrome_in_source = sum(1 for it in items if it.get("type") in CHROME_TYPES)
    assert chrome_in_source == 4
    assert all(c.type != "chrome" for c in chunks)
    # Running header text must not survive as a chunk.
    assert not any("Chapter 28. Latent factor models" in c.content for c in chunks)
    assert not any(c.content == "956" for c in chunks)  # page number gone


def test_heading_is_text_with_level_not_header_type(items: list[dict]) -> None:
    headings = [c for c in parse_content_list(items) if c.type == "heading"]
    assert len(headings) == 1
    h = headings[0]
    assert h.content == "28.4.2 Multinomial PCA"
    assert h.text_level == 2


def test_body_text(items: list[dict]) -> None:
    bodies = [c for c in parse_content_list(items) if c.type == "text"]
    assert any("Dirichlet prior" in c.content for c in bodies)
    assert all(c.text_level is None for c in bodies)


def test_equation_latex_preserved(items: list[dict]) -> None:
    eqs = [c for c in parse_content_list(items) if c.type == "equation"]
    assert len(eqs) == 1
    assert eqs[0].text_format == "latex"
    assert eqs[0].content.startswith("$$") and eqs[0].content.endswith("$$")
    assert r"\mathrm{Dir}" in eqs[0].content


def test_image_caption_and_path(items: list[dict]) -> None:
    images = [c for c in parse_content_list(items) if c.type == "image"]
    # fixture: 1 image + 1 chart (→image) + 1 multi-caption image = 3
    assert len(images) == 3
    fig1 = next(c for c in images if c.img_path == "images/fig1.jpg")
    assert fig1.caption == "Figure 28.20: Simplex FA model as a DPGM."


def test_chart_becomes_image_keeps_content(items: list[dict]) -> None:
    chart = next(c for c in parse_content_list(items) if c.img_path == "images/chart1.jpg")
    assert chart.type == "image"
    assert chart.content == "bar chart: A=3 B=5"
    assert chart.caption == "Figure 28.X: results"


def test_multiple_captions_joined(items: list[dict]) -> None:
    fig2 = next(c for c in parse_content_list(items) if c.img_path == "images/fig2.jpg")
    assert fig2.caption == "Cap A Cap B"


def test_missing_bbox_becomes_empty_list(items: list[dict]) -> None:
    no_bbox = next(c for c in parse_content_list(items) if c.content == "Body with no bbox")
    assert no_bbox.bbox_json == "[]"


def test_table_type(items: list[dict]) -> None:
    tables = [c for c in parse_content_list(items) if c.type == "table"]
    assert len(tables) == 1
    assert "| a | b |" in tables[0].content


def test_unknown_type_preserved_not_dropped(items: list[dict]) -> None:
    unknown = [c for c in parse_content_list(items) if c.type == "unknown"]
    assert len(unknown) == 1
    assert unknown[0].content == "unknown content"


def test_order_idx_is_gapless_over_kept_items(items: list[dict]) -> None:
    chunks = parse_content_list(items)
    assert [c.order_idx for c in chunks] == list(range(len(chunks)))


def test_page_idx_preserved(items: list[dict]) -> None:
    chunks = parse_content_list(items)
    # page 0, 1, 2 all represented
    assert {c.page_idx for c in chunks} == {0, 1, 2}


def test_bbox_verbatim_float(items: list[dict]) -> None:
    eq = next(c for c in parse_content_list(items) if c.type == "equation")
    assert json.loads(eq.bbox_json) == [149.0, 150.0, 520.0, 200.0]


def test_missing_page_idx_rejects_document() -> None:
    with pytest.raises(ContentListError, match="missing page_idx"):
        parse_content_list([{"type": "text", "text": "x"}])


def test_non_int_page_idx_rejects() -> None:
    with pytest.raises(ContentListError, match="non-int page_idx"):
        parse_content_list([{"type": "text", "text": "x", "page_idx": "abc"}])


def test_non_list_input_rejects() -> None:
    with pytest.raises(ContentListError, match="must be a list"):
        parse_content_list({"type": "text"})  # type: ignore[arg-type]


def test_empty_text_item_skipped() -> None:
    chunks = parse_content_list(
        [
            {"type": "text", "text": "   ", "page_idx": 0},
            {"type": "text", "text": "real", "page_idx": 0},
        ]
    )
    assert len(chunks) == 1
    assert chunks[0].content == "real"
