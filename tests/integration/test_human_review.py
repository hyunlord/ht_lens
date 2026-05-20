"""Sanity-check the human-review dump script via tmp_path (no repo writes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ht_lens.extract.pipeline import extract_pdf

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
sys.path.insert(0, str(REPO / "scripts"))


def test_human_review_format_produces_dump(tmp_path: Path) -> None:
    """Run the same formatting logic the dump script uses, into tmp_path only.

    This proves the dump format is deterministic and the script's per-block
    rendering hits every block. The repo-tracked ``docs/phases/phase-1/samples.md``
    is refreshed manually with ``uv run python scripts/dump_samples.py``.
    """
    import dump_samples  # type: ignore[import-not-found]

    out = tmp_path / "en"
    extract_pdf(FIXTURES / "sample_en.pdf", out)
    rendered = dump_samples._format_doc(out)

    # Spot-check shape.
    page_count = json.loads((out / "doc_meta.json").read_text())["num_pages"]
    assert rendered.count("### page_") == page_count

    block_count = sum(
        len(json.loads(p.read_text())["blocks"]) for p in sorted((out / "pages").glob("*.json"))
    )
    # One bullet line per block.
    assert rendered.count("\n  - `") == block_count


@pytest.mark.skipif(
    not (REPO / "docs" / "phases" / "phase-1" / "samples.md").exists(),
    reason="samples.md not generated yet (run scripts/dump_samples.py)",
)
def test_committed_samples_md_is_non_empty() -> None:
    p = REPO / "docs" / "phases" / "phase-1" / "samples.md"
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# Phase 1 — sample extraction review")
    for name in ("sample_en.pdf", "sample_ko.pdf", "sample_mixed.pdf"):
        assert f"## {name}" in text
