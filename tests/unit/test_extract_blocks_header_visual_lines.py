"""Phase 6h-1 — header detection uses VISUAL line count, not raw line count.

If a header is split across multiple PyMuPDF "lines" on the same visual
line (e.g., section number + section title with a horizontal gap), the
old logic counted raw lines and could demote a 3-fragment title to
``text``. The fix counts visual lines via :func:`_count_visual_lines`.
"""

from __future__ import annotations

from ht_lens.extract._fitz import RawBlock, RawLine, RawPage, RawSpan
from ht_lens.extract.blocks import group_page


def _span(text: str, size: float, bbox: tuple[float, float, float, float]) -> RawSpan:
    return RawSpan(text=text, bbox=bbox, font="Times", size=size, flags=0)


def _line(
    text: str,
    y0: float,
    y1: float,
    *,
    x0: float = 72.0,
    x1: float = 540.0,
    size: float = 12.0,
) -> RawLine:
    bbox = (x0, y0, x1, y1)
    return RawLine(bbox=bbox, spans=(_span(text, size, bbox),), direction=(1.0, 0.0))


def _page(blocks: list[RawBlock]) -> RawPage:
    return RawPage(page_num=1, width=612.0, height=792.0, rotation=0, blocks=tuple(blocks))


def _text_block(lines: list[RawLine]) -> RawBlock:
    x0 = min(ln.bbox[0] for ln in lines)
    y0 = min(ln.bbox[1] for ln in lines)
    x1 = max(ln.bbox[2] for ln in lines)
    y1 = max(ln.bbox[3] for ln in lines)
    return RawBlock(bbox=(x0, y0, x1, y1), block_type="text", lines=tuple(lines))


def test_header_split_into_3_horizontal_fragments_still_classified_as_header() -> None:
    """A title split into 3 same-visual-line fragments must still be a header.

    Pre-Phase 6h-1 the heuristic used ``len(para_lines) <= 2`` which would
    demote this to ``text``. Now ``_count_visual_lines`` collapses the 3
    fragments into one visual line.
    """
    # Header (size 20) split into 3 horizontal pieces at the same y.
    header_lines = [
        _line("22.4.3", 90.0, 110.0, x0=72.0, x1=120.0, size=20.0),
        _line("Other", 90.0, 110.0, x0=130.0, x1=180.0, size=20.0),
        _line("Applications", 90.0, 110.0, x0=190.0, x1=300.0, size=20.0),
    ]
    # Body at size 12 (so the page median size is 12; header size 20 > 1.4 * 12).
    body_lines = [
        _line(f"body line {i}", 200.0 + i * 14, 212.0 + i * 14, size=12.0) for i in range(10)
    ]
    grouped = group_page(_page([_text_block(header_lines), _text_block(body_lines)]))
    # Find the header-classified block.
    headers = [g for g in grouped if g.type == "header"]
    assert len(headers) == 1, f"expected 1 header, got {[g.type for g in grouped]}"
    assert headers[0].text == "22.4.3 Other Applications"


def test_multi_visual_line_title_above_max_is_text_not_header() -> None:
    """Conversely, a paragraph with >2 DISTINCT visual lines should be
    ``text`` even if each line has header-sized font."""
    # 3 visual lines, each at a different y range, same big font.
    lines = [
        _line("Title line 1", 80.0, 100.0, size=20.0),
        _line("Title line 2", 105.0, 125.0, size=20.0),
        _line("Title line 3", 130.0, 150.0, size=20.0),
    ]
    body = [_line(f"body {i}", 200.0 + i * 14, 212.0 + i * 14, size=12.0) for i in range(10)]
    grouped = group_page(_page([_text_block(lines), _text_block(body)]))
    # The 3-visual-line block must not be a header — visual count > 2.
    candidates = [
        g for g in grouped if g.text.startswith("Title line 1") and "Title line 3" in g.text
    ]
    assert candidates, f"expected the title block to be present, got {grouped}"
    assert candidates[0].type == "text"
