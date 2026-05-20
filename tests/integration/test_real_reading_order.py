"""Anchored reading-order assertions against the real fixture PDFs.

These guard against silent regressions on the actual ROADMAP-cited risk
("멀티컬럼 reading order"). Synthetic unit tests prove the algorithm; this
proves it survives the fixtures we have.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest

from ht_lens.extract.pipeline import extract_pdf

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module")
def en_page1_blocks(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    out = tmp_path_factory.mktemp("real_ro_en")
    extract_pdf(FIXTURES / "sample_en.pdf", out)
    page1 = json.loads((out / "pages" / "page_0001.json").read_text())
    return list(page1["blocks"])


@pytest.fixture(scope="module")
def ko_page5_blocks(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    out = tmp_path_factory.mktemp("real_ro_ko")
    extract_pdf(FIXTURES / "sample_ko.pdf", out)
    page5 = json.loads((out / "pages" / "page_0005.json").read_text())
    return list(page5["blocks"])


def test_arxiv_title_block_appears_in_first_third_of_page(
    en_page1_blocks: list[dict],
) -> None:
    """The Open-Sora paper title must lead the cover page, not trail it."""
    titles = [
        i
        for i, b in enumerate(en_page1_blocks)
        if "Open-Sora" in b["text"] and "Training" in b["text"]
    ]
    assert titles, "title block not found"
    first_title_idx = titles[0]
    assert first_title_idx < len(en_page1_blocks) // 3, (
        f"title appeared at position {first_title_idx} of {len(en_page1_blocks)}, "
        "expected within the first third"
    )


def test_arxiv_intro_heading_appears_after_title(
    en_page1_blocks: list[dict],
) -> None:
    """'1 Introduction' is a section heading; it must follow the title."""
    title_positions = [
        i for i, b in enumerate(en_page1_blocks) if "Training a Commercial-Level Video" in b["text"]
    ]
    intro_positions = [i for i, b in enumerate(en_page1_blocks) if "Introduction" in b["text"]]
    assert title_positions and intro_positions
    assert max(title_positions) < min(intro_positions), (
        "Introduction heading came before the title; reading order regressed"
    )


def test_ko_page_blocks_are_y_monotonic_modulo_small_jitter(
    ko_page5_blocks: list[dict],
) -> None:
    """Korean fixture page 5 mixes wide body paragraphs with images and headers.

    Earlier versions lifted wide body blocks above narrow top-of-page content,
    producing a visible regression in samples.md. Reading order should now be
    broadly top-to-bottom: each block's y0 must be no smaller than the previous
    block's y0 by more than half a page-height.
    """
    ys = [b["bbox"][1] for b in ko_page5_blocks]
    page_height = 842.9
    for prev, cur in pairwise(ys):
        assert cur >= prev - page_height / 2, (
            f"large backward jump {prev:.1f} → {cur:.1f} indicates reading-order regression"
        )


def test_ko_page_top_block_appears_first(ko_page5_blocks: list[dict]) -> None:
    """Whatever block has the smallest y0 must be inside the first half of the page output."""
    ys = [(i, b["bbox"][1]) for i, b in enumerate(ko_page5_blocks)]
    top_idx = min(ys, key=lambda iy: iy[1])[0]
    assert top_idx < len(ko_page5_blocks) // 2, (
        f"top-of-page block landed at index {top_idx} of {len(ko_page5_blocks)}"
    )
