"""Anchored reading-order assertions against the real fixture PDFs.

These guard against silent regressions on the actual ROADMAP-cited risk
("멀티컬럼 reading order"). Synthetic unit tests prove the algorithm; this
proves it survives the fixtures we have.
"""

from __future__ import annotations

import json
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
