"""Paragraph grouping and header detection."""

from __future__ import annotations

from ht_lens.extract._fitz import RawBlock, RawLine, RawPage, RawSpan
from ht_lens.extract.blocks import group_page


def _span(text: str, size: float, bbox: tuple[float, float, float, float]) -> RawSpan:
    return RawSpan(text=text, bbox=bbox, font="Times", size=size, flags=0)


def _line(text: str, size: float, y: float, height: float = 12.0) -> RawLine:
    bbox = (72.0, y, 540.0, y + height)
    return RawLine(bbox=bbox, spans=(_span(text, size, bbox),), direction=(1.0, 0.0))


def _text_block(lines: list[RawLine]) -> RawBlock:
    x0 = min(ln.bbox[0] for ln in lines)
    y0 = min(ln.bbox[1] for ln in lines)
    x1 = max(ln.bbox[2] for ln in lines)
    y1 = max(ln.bbox[3] for ln in lines)
    return RawBlock(bbox=(x0, y0, x1, y1), block_type="text", lines=tuple(lines))


def _page(blocks: list[RawBlock]) -> RawPage:
    return RawPage(
        page_num=1, width=612.0, height=792.0, rotation=0, blocks=tuple(blocks)
    )


def test_consecutive_lines_merge_into_single_paragraph() -> None:
    lines = [_line("Hello world line 1.", 12.0, 100.0), _line("Continuation here.", 12.0, 112.0)]
    page = _page([_text_block(lines)])
    grouped = group_page(page)
    assert len(grouped) == 1
    assert grouped[0].type == "text"
    assert grouped[0].text == "Hello world line 1.\nContinuation here."


def test_large_y_gap_splits_paragraphs() -> None:
    lines = [_line("First para.", 12.0, 100.0), _line("Second para.", 12.0, 200.0)]
    page = _page([_text_block(lines)])
    grouped = group_page(page)
    assert len(grouped) == 2


def test_header_detected_by_font_size_ratio() -> None:
    body_lines = [_line(f"body line {i}", 12.0, 200.0 + i * 14) for i in range(10)]
    header_block = _text_block([_line("Title", 20.0, 90.0, height=20)])
    body_block = _text_block(body_lines)
    page = _page([header_block, body_block])

    grouped = group_page(page)
    types = [g.type for g in grouped]
    assert "header" in types
    header = next(g for g in grouped if g.type == "header")
    assert header.text == "Title"


def test_image_block_preserved_with_empty_text() -> None:
    image = RawBlock(bbox=(100.0, 100.0, 300.0, 250.0), block_type="image", lines=())
    grouped = group_page(_page([image]))
    assert len(grouped) == 1
    assert grouped[0].type == "image"
    assert grouped[0].text == ""


def test_empty_text_block_dropped() -> None:
    blank = _text_block([_line("   ", 12.0, 100.0)])
    grouped = group_page(_page([blank]))
    assert grouped == []
