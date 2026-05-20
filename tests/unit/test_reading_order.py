"""Reading order: single column trust + multi-column fallback."""

from __future__ import annotations

from ht_lens.extract.blocks import GroupedBlock
from ht_lens.extract.reading_order import order_blocks

PAGE_W = 600.0


def _block(text: str, x0: float, y0: float, x1: float, y1: float, type_: str = "text") -> GroupedBlock:
    return GroupedBlock(bbox=(x0, y0, x1, y1), type=type_, text=text)  # type: ignore[arg-type]


def test_single_column_keeps_input_order_when_monotonic() -> None:
    blocks = [_block(f"line {i}", 72, 100 + i * 20, 540, 110 + i * 20) for i in range(5)]
    ordered = order_blocks(blocks, page_width=PAGE_W)
    assert [b.text for b in ordered] == [f"line {i}" for i in range(5)]


def test_two_columns_with_y_regression_resorted_left_then_right() -> None:
    # Simulate the kind of messy ordering PyMuPDF emits when it loses
    # the column structure: the y values regress at least twice.
    blocks = [
        _block("L0", 60, 100, 290, 115),
        _block("R0", 310, 130, 540, 145),
        _block("L1", 60, 110, 290, 125),  # y regresses (130 -> 110)
        _block("R1", 310, 140, 540, 155),
        _block("L2", 60, 120, 290, 135),  # y regresses again (140 -> 120)
        _block("R2", 310, 150, 540, 165),
    ]
    ordered = order_blocks(blocks, page_width=PAGE_W)
    assert [b.text for b in ordered] == ["L0", "L1", "L2", "R0", "R1", "R2"]


def test_spanning_header_pulled_above_columns() -> None:
    header = _block("HEADER", 60, 70, 540, 90, type_="header")
    blocks = [
        _block("L0", 60, 100, 290, 115),
        _block("R0", 310, 130, 540, 145),
        _block("L1", 60, 110, 290, 125),  # regression
        _block("R1", 310, 140, 540, 155),
        header,  # final block forces another regression
    ]
    ordered = order_blocks(blocks, page_width=PAGE_W)
    assert ordered[0].text == "HEADER"
    assert [b.text for b in ordered[1:]] == ["L0", "L1", "R0", "R1"]


def test_indented_bullets_do_not_create_separate_columns() -> None:
    # Slight indent (40pt) on bullet lines should NOT split into a column.
    body = [
        _block(f"para {i}", 72, 100 + i * 20, 540, 115 + i * 20) for i in range(3)
    ]
    bullets = [
        _block("- bullet 0", 100, 160 + i * 20, 540, 175 + i * 20) for i in range(2)
    ]
    blocks = body + bullets
    ordered = order_blocks(blocks, page_width=PAGE_W)
    # Should remain in y order (single column).
    ys = [b.bbox[1] for b in ordered]
    assert ys == sorted(ys)


def test_empty_or_single_block_returns_input() -> None:
    assert order_blocks([], page_width=PAGE_W) == []
    one = [_block("only", 72, 100, 540, 115)]
    assert order_blocks(one, page_width=PAGE_W) == one
