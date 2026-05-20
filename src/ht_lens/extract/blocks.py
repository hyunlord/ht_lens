"""Paragraph grouping and header detection from RawBlock/RawLine."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from statistics import median
from typing import Literal

from ht_lens.extract._fitz import RawBlock, RawLine, RawPage

GroupedType = Literal["text", "image", "header"]

_HEADER_SIZE_RATIO = 1.4
_HEADER_MAX_LINES = 2
_PARA_GAP_SAME = 0.5
_PARA_GAP_BREAK = 1.2
_FONT_SIZE_BREAK = 0.20


@dataclass(frozen=True)
class GroupedBlock:
    bbox: tuple[float, float, float, float]
    type: GroupedType
    text: str


def _line_text(line: RawLine) -> str:
    return "".join(span.text for span in line.spans)


def _line_size(line: RawLine) -> float:
    sizes = [span.size for span in line.spans if span.size > 0]
    return median(sizes) if sizes else 0.0


def _line_height(line: RawLine) -> float:
    return float(line.bbox[3] - line.bbox[1])


def _union(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return (x0, y0, x1, y1)


def _group_lines_into_paragraphs(lines: list[RawLine]) -> list[list[RawLine]]:
    """Split a block's lines into paragraphs by vertical gap and font-size shift."""
    if not lines:
        return []
    sorted_lines = sorted(lines, key=lambda ln: (ln.bbox[1], ln.bbox[0]))
    heights = [_line_height(ln) for ln in sorted_lines if _line_height(ln) > 0]
    med_h = median(heights) if heights else 12.0

    paragraphs: list[list[RawLine]] = [[sorted_lines[0]]]
    for prev, cur in pairwise(sorted_lines):
        gap = cur.bbox[1] - prev.bbox[3]
        prev_size = _line_size(prev)
        cur_size = _line_size(cur)
        font_break = (
            prev_size > 0
            and cur_size > 0
            and abs(prev_size - cur_size) / max(prev_size, cur_size) > _FONT_SIZE_BREAK
        )
        if gap > _PARA_GAP_BREAK * med_h or font_break:
            paragraphs.append([cur])
        elif gap <= _PARA_GAP_SAME * med_h:
            paragraphs[-1].append(cur)
        else:
            paragraphs[-1].append(cur)
    return paragraphs


def _page_median_font_size(blocks: list[RawBlock]) -> float:
    sizes: list[float] = []
    for blk in blocks:
        if blk.block_type != "text":
            continue
        for line in blk.lines:
            for span in line.spans:
                if span.size > 0:
                    sizes.append(span.size)
    return median(sizes) if sizes else 12.0


def group_page(page: RawPage) -> list[GroupedBlock]:
    """Convert raw PyMuPDF blocks to grouped paragraph/header/image blocks."""
    median_size = _page_median_font_size(list(page.blocks))
    grouped: list[GroupedBlock] = []

    for blk in page.blocks:
        if blk.block_type == "image":
            grouped.append(GroupedBlock(bbox=blk.bbox, type="image", text=""))
            continue

        paragraphs = _group_lines_into_paragraphs(list(blk.lines))
        for para_lines in paragraphs:
            text = "\n".join(_line_text(ln).rstrip() for ln in para_lines).strip()
            if not text:
                continue
            bbox = _union([ln.bbox for ln in para_lines])
            sizes = [_line_size(ln) for ln in para_lines if _line_size(ln) > 0]
            avg_size = median(sizes) if sizes else median_size
            is_header = (
                avg_size >= _HEADER_SIZE_RATIO * median_size
                and len(para_lines) <= _HEADER_MAX_LINES
            )
            grouped.append(
                GroupedBlock(
                    bbox=bbox,
                    type="header" if is_header else "text",
                    text=text,
                )
            )

    return grouped
