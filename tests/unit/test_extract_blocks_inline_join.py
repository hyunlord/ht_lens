"""Phase 6h-1 — Y-overlap inline-join logic.

Locks the helpers that decide whether two PyMuPDF "lines" should join
with a single space (because they share a visual line; e.g.,
``"22.4.3"`` + ``"Other applications"`` separated by a horizontal gap)
versus a newline (genuine multi-line content). Each test pins one
contract from the V2 plan.
"""

from __future__ import annotations

from ht_lens.extract._fitz import RawBlock, RawLine, RawPage, RawSpan
from ht_lens.extract.blocks import (
    _join_lines,
    _should_concat_inline,
    group_page,
)


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
    direction: tuple[float, float] = (1.0, 0.0),
) -> RawLine:
    bbox = (x0, y0, x1, y1)
    return RawLine(bbox=bbox, spans=(_span(text, size, bbox),), direction=direction)


def _page_with_one_block(lines: list[RawLine]) -> RawPage:
    x0 = min(ln.bbox[0] for ln in lines)
    y0 = min(ln.bbox[1] for ln in lines)
    x1 = max(ln.bbox[2] for ln in lines)
    y1 = max(ln.bbox[3] for ln in lines)
    block = RawBlock(bbox=(x0, y0, x1, y1), block_type="text", lines=tuple(lines))
    return RawPage(page_num=1, width=612.0, height=792.0, rotation=0, blocks=(block,))


def test_single_line_block_unchanged() -> None:
    """One RawLine → text and bbox unchanged from input."""
    ln = _line("Hello world.", 100.0, 112.0, x0=72.0, x1=200.0)
    grouped = group_page(_page_with_one_block([ln]))
    assert len(grouped) == 1
    g = grouped[0]
    assert g.text == "Hello world."
    assert g.bbox == (72.0, 100.0, 200.0, 112.0)


def test_y_overlap_lines_joined_with_space() -> None:
    """Same y range, different x → space-join, bbox is x-union, single-line height."""
    # "22.4.3" + "Other applications" both at y=61.5-72.4
    left = _line("22.4.3", 61.5, 72.4, x0=77.0, x1=108.8)
    right = _line("Other applications", 61.5, 72.4, x0=121.3, x1=222.2)
    grouped = group_page(_page_with_one_block([left, right]))
    assert len(grouped) == 1
    g = grouped[0]
    assert g.text == "22.4.3 Other applications"
    # x-union, height unchanged
    assert g.bbox == (77.0, 61.5, 222.2, 72.4)


def test_y_distinct_lines_joined_with_newline() -> None:
    """Different y ranges → newline-join (existing multi-line behavior)."""
    first = _line("First line.", 100.0, 112.0, x0=72.0, x1=200.0)
    second = _line("Second line.", 113.0, 125.0, x0=72.0, x1=200.0)
    grouped = group_page(_page_with_one_block([first, second]))
    assert len(grouped) == 1
    g = grouped[0]
    assert g.text == "First line.\nSecond line."
    assert g.bbox == (72.0, 100.0, 200.0, 125.0)


def test_should_concat_inline_threshold_60pct() -> None:
    """Y-overlap < 60% → newline; >= 60% → space (with similar height + both horizontal)."""
    # Two 10-tall lines; vary cur's y0 to control overlap.
    prev = _line("a", 100.0, 110.0)  # height 10
    # 60% overlap requires overlap >= 6 (60% of min height 10).
    # Place cur at y0=104 → overlap = min(110,114) - max(100,104) = 110-104 = 6 → exactly 60% → True
    cur_60 = _line("b", 104.0, 114.0)
    assert _should_concat_inline(prev, cur_60) is True

    # cur at y0=105 → overlap=5 = 50% → False
    cur_50 = _line("b", 105.0, 115.0)
    assert _should_concat_inline(prev, cur_50) is False


def test_should_concat_inline_rejects_non_horizontal() -> None:
    """Rotation safety: vertical writing direction must never inline-join."""
    prev_h = _line("a", 100.0, 110.0, direction=(1.0, 0.0))
    # Same y range as prev, but direction is vertical.
    cur_v = _line("b", 100.0, 110.0, x0=200.0, x1=210.0, direction=(0.0, 1.0))
    assert _should_concat_inline(prev_h, cur_v) is False
    assert _should_concat_inline(cur_v, prev_h) is False
    # Both vertical: also rejected (the y-overlap heuristic does not
    # apply to vertical writing).
    cur_v2 = _line("c", 100.0, 110.0, x0=220.0, x1=230.0, direction=(0.0, 1.0))
    assert _should_concat_inline(cur_v, cur_v2) is False


def test_should_concat_inline_rejects_height_mismatch() -> None:
    """Superscript/subscript guard: when one line is much smaller, do not join."""
    main = _line("x", 100.0, 112.0)  # height 12
    # superscript "2" at smaller size, height 6, partially overlapping y
    sup = _line("2", 100.0, 106.0, x0=110.0, x1=115.0, size=6.0)
    # height ratio = 6/12 = 0.5 < 0.7 → False even though y-overlap is high
    assert _should_concat_inline(main, sup) is False


def test_join_lines_mixed_paragraph_three_pieces() -> None:
    """3-fragment paragraph: two same-line + one newline."""
    a = _line("22.5", 120.0, 131.9, x0=77.0, x1=100.9)
    b = _line("Large Language Models", 120.0, 131.9, x0=114.3, x1=303.6)
    c = _line("Body line.", 145.0, 157.0, x0=77.0, x1=200.0)
    text = _join_lines([a, b, c])
    assert text == "22.5 Large Language Models\nBody line."
