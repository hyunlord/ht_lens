"""Generate a human-review artifact for DoD evidence."""

from __future__ import annotations

import json
from pathlib import Path

from ht_lens.extract.pipeline import extract_pdf

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DOCS_OUT = Path(__file__).resolve().parents[2] / "docs" / "phases" / "phase-1"


def _format_doc(out: Path) -> str:
    meta = json.loads((out / "doc_meta.json").read_text())
    lines: list[str] = []
    lines.append(f"## {meta['filename']}")
    lines.append("")
    lines.append(f"- num_pages: {meta['num_pages']}")
    lines.append(f"- lang_guess: {meta['lang_guess']}")
    lines.append("")
    for jpath in sorted((out / "pages").glob("page_*.json")):
        page = json.loads(jpath.read_text())
        lines.append(f"### {jpath.name} (page {page['page_num']})")
        lines.append("")
        lines.append(f"- size: {page['width']}x{page['height']}pt, rotation={page['rotation']}")
        lines.append(f"- blocks: {len(page['blocks'])}")
        for blk in page["blocks"]:
            text = blk["text"].replace("\n", " ⏎ ")[:60]
            lines.append(f"  - `{blk['id']}` {blk['type']:6s} bbox={blk['bbox']} text={text!r}")
        lines.append("")
    return "\n".join(lines)


def test_generate_samples_md(tmp_path: Path) -> None:
    DOCS_OUT.mkdir(parents=True, exist_ok=True)
    sections: list[str] = ["# Phase 1 — sample extraction review", ""]
    for name in ("sample_en.pdf", "sample_ko.pdf", "sample_mixed.pdf"):
        out = tmp_path / name.replace(".pdf", "")
        extract_pdf(FIXTURES / name, out)
        sections.append(_format_doc(out))
    (DOCS_OUT / "samples.md").write_text("\n".join(sections), encoding="utf-8")
    assert (DOCS_OUT / "samples.md").exists()
