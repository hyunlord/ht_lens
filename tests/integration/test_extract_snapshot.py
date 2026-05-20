"""Snapshot tests for extracted block structure (normalized)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from ht_lens.extract.normalize import normalize_doc_meta, normalize_page
from ht_lens.extract.pipeline import extract_pdf

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _normalized_summary(out: Path) -> dict[str, object]:
    pages = []
    for jpath in sorted((out / "pages").glob("page_*.json")):
        pages.append(normalize_page(json.loads(jpath.read_text())))
    doc_meta = normalize_doc_meta(json.loads((out / "doc_meta.json").read_text()))
    return {"doc_meta": doc_meta, "pages": pages}


@pytest.mark.parametrize(
    "sample_name",
    ["sample_en.pdf", "sample_ko.pdf", "sample_mixed.pdf"],
)
def test_extract_snapshot(sample_name: str, tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    out = tmp_path / "out"
    extract_pdf(FIXTURES / sample_name, out)
    summary = _normalized_summary(out)
    assert summary == snapshot(name=sample_name)
