"""Phase 6h-1 — KPI synthetic test.

Plan V2 §Sub-goal 2 (test 9). Real-world audit numbers
(``ROADMAP`` Pattern A: 6,912 leak blocks system-wide) cannot be
re-measured here without backfill against real corpora; this test
instead pins the *logic* on a synthetic input — N synthesized
multi-fragment paragraphs each get collapsed into one visual line
after the fix.
"""

from __future__ import annotations

from ht_lens.extract._fitz import RawBlock, RawLine, RawPage, RawSpan
from ht_lens.extract.blocks import group_page


def _line(
    text: str,
    y0: float,
    y1: float,
    x0: float,
    x1: float,
    size: float = 12.0,
) -> RawLine:
    bbox = (x0, y0, x1, y1)
    span = RawSpan(text=text, bbox=bbox, font="Times", size=size, flags=0)
    return RawLine(bbox=bbox, spans=(span,), direction=(1.0, 0.0))


def _text_block(lines: list[RawLine]) -> RawBlock:
    x0 = min(ln.bbox[0] for ln in lines)
    y0 = min(ln.bbox[1] for ln in lines)
    x1 = max(ln.bbox[2] for ln in lines)
    y1 = max(ln.bbox[3] for ln in lines)
    return RawBlock(bbox=(x0, y0, x1, y1), block_type="text", lines=tuple(lines))


def test_pattern_a_fix_collapses_inline_split_lines() -> None:
    """Synthesize 50 paragraphs that each look like
    ``"sec.num"`` + ``"section title"`` at the same y. After
    ``group_page``, every paragraph must collapse to a single GroupedBlock
    whose ``text`` contains no ``\\n`` (space-joined) and whose bbox
    spans both fragments horizontally.
    """
    blocks: list[RawBlock] = []
    for i in range(50):
        y0 = 100.0 + i * 20.0
        y1 = y0 + 12.0
        left = _line(f"{i + 1}.0", y0, y1, x0=72.0, x1=110.0)
        right = _line(f"Section title {i + 1}", y0, y1, x0=130.0, x1=300.0)
        blocks.append(_text_block([left, right]))

    grouped = group_page(
        RawPage(page_num=1, width=612.0, height=2000.0, rotation=0, blocks=tuple(blocks))
    )

    assert len(grouped) == 50, f"each paragraph should remain one block, got {len(grouped)}"
    collapsed = sum(1 for g in grouped if "\n" not in g.text)
    assert collapsed == 50, (
        f"Phase 6h-1 fix should collapse all 50 Pattern A paragraphs into "
        f"single-visual-line text; only {collapsed}/50 are \\n-free"
    )
    # Spot-check the first one — both fragments present, in correct order.
    assert grouped[0].text == "1.0 Section title 1"


def test_distinct_visual_lines_preserve_newline() -> None:
    """Inverse contract: real multi-line paragraphs must keep ``\\n``.

    Synthesize 30 paragraphs each with 3 vertically-distinct lines.
    After group_page, every paragraph should have exactly 2 ``\\n``
    characters in its text.
    """
    blocks: list[RawBlock] = []
    for i in range(30):
        y_base = 100.0 + i * 60.0
        lines = [
            _line(f"line A {i + 1}", y_base + 0, y_base + 12, x0=72.0, x1=300.0),
            _line(f"line B {i + 1}", y_base + 13, y_base + 25, x0=72.0, x1=300.0),
            _line(f"line C {i + 1}", y_base + 26, y_base + 38, x0=72.0, x1=300.0),
        ]
        blocks.append(_text_block(lines))

    grouped = group_page(
        RawPage(page_num=1, width=612.0, height=3000.0, rotation=0, blocks=tuple(blocks))
    )
    multi_line = sum(1 for g in grouped if g.text.count("\n") == 2)
    assert multi_line == 30, (
        f"distinct-y multi-line content should keep \\n; got {multi_line}/30 with 2 newlines"
    )
