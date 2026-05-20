"""Regenerate docs/phases/phase-1/samples.md from the fixture extractions.

Usage:
    uv run python scripts/dump_samples.py

Outputs a deterministic per-block dump (id/type/bbox/order/first-60-chars) for
each fixture PDF. The file is human-review evidence for the DoD line
"block JSON이 사람이 봐도 합리적".
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ht_lens.extract.pipeline import extract_pdf

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
OUT_FILE = REPO / "docs" / "phases" / "phase-1" / "samples.md"


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


def main() -> None:
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    sections: list[str] = ["# Phase 1 — sample extraction review", ""]
    with tempfile.TemporaryDirectory() as tmp_root:
        for name in ("sample_en.pdf", "sample_ko.pdf", "sample_mixed.pdf"):
            out = Path(tmp_root) / name.replace(".pdf", "")
            extract_pdf(FIXTURES / name, out)
            sections.append(_format_doc(out))
    OUT_FILE.write_text("\n".join(sections), encoding="utf-8")
    print(f"wrote {OUT_FILE} ({OUT_FILE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
