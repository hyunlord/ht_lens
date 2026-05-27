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
_HEADER_MIN_SIZE_PT = 13.0
_HEADER_MIN_CHARS = 3
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


def _is_horizontal(line: RawLine) -> bool:
    """True iff the line's writing direction is closer to horizontal than vertical."""
    dx, dy = line.direction
    return abs(dx) >= abs(dy)


# Phase 6h-1: thresholds for detecting that two PyMuPDF "lines" actually
# render on the same visual line (e.g., "22.4.3" + "Other applications"
# separated by a horizontal gap). 60% y-overlap + height-similar + both
# horizontal — tuned so superscript/subscript fragments and rotated
# pages do NOT trigger inline join.
_INLINE_JOIN_Y_OVERLAP = 0.6
_INLINE_JOIN_HEIGHT_RATIO = 0.7


def _should_concat_inline(prev: RawLine, cur: RawLine) -> bool:
    """Return True iff two consecutive raw lines render on the same visual line.

    PyMuPDF emits separate ``lines`` when there is a horizontal gap (tab,
    multi-column spacing). The y-ranges are then identical and our
    paragraph grouper keeps them in the same paragraph, so the naive
    ``"\\n".join(...)`` produces multi-line stored text from what is
    visually one line. This helper guards space-vs-newline by requiring
    all three of:

    1. Both lines are horizontal (avoids touching rotated/vertical text
       that the rest of the pipeline already handles separately).
    2. Their bbox heights are similar (rejects superscript/subscript
       fragments whose bbox is much smaller).
    3. Their y-ranges overlap by >= ``_INLINE_JOIN_Y_OVERLAP`` of the
       smaller line height.
    """
    if not _is_horizontal(prev) or not _is_horizontal(cur):
        return False
    py0, py1 = prev.bbox[1], prev.bbox[3]
    cy0, cy1 = cur.bbox[1], cur.bbox[3]
    prev_h = max(py1 - py0, 1e-6)
    cur_h = max(cy1 - cy0, 1e-6)
    if min(prev_h, cur_h) / max(prev_h, cur_h) < _INLINE_JOIN_HEIGHT_RATIO:
        return False
    overlap = max(0.0, min(py1, cy1) - max(py0, cy0))
    return overlap >= _INLINE_JOIN_Y_OVERLAP * min(prev_h, cur_h)


def _join_lines(lines: list[RawLine]) -> str:
    """Phase 6h-1: join paragraph lines with space when same-visual-line,
    ``\\n`` otherwise. See :func:`_should_concat_inline`."""
    if not lines:
        return ""
    parts: list[str] = [_line_text(lines[0]).rstrip()]
    for prev, cur in pairwise(lines):
        sep = " " if _should_concat_inline(prev, cur) else "\n"
        parts.append(sep + _line_text(cur).rstrip())
    return "".join(parts).strip()


def _count_visual_lines(lines: list[RawLine]) -> int:
    """Phase 6h-1: count semantic visual lines.

    Consecutive raw lines that share a visual line (per
    :func:`_should_concat_inline`) count as one. Used by the header
    heuristic so a title split into 3 horizontal fragments still passes
    ``len(visual_lines) <= _HEADER_MAX_LINES``.
    """
    if not lines:
        return 0
    n = 1
    for prev, cur in pairwise(lines):
        if not _should_concat_inline(prev, cur):
            n += 1
    return n


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
            # Phase 6h-1: join with space when consecutive raw lines share
            # the same visual line (PyMuPDF often emits separate ``lines``
            # for one-line text with a horizontal gap); ``\\n`` otherwise.
            text = _join_lines(para_lines)
            if not text:
                continue
            bbox = _union([ln.bbox for ln in para_lines])
            sizes = [_line_size(ln) for ln in para_lines if _line_size(ln) > 0]
            avg_size = median(sizes) if sizes else median_size
            all_horizontal = all(_is_horizontal(ln) for ln in para_lines)
            # Phase 6h-1: count visual lines, not raw lines, so a header
            # split into multiple horizontal fragments still qualifies.
            is_header = (
                all_horizontal
                and avg_size >= _HEADER_SIZE_RATIO * median_size
                and avg_size >= _HEADER_MIN_SIZE_PT
                and _count_visual_lines(para_lines) <= _HEADER_MAX_LINES
                and len(text.replace("\n", "").strip()) >= _HEADER_MIN_CHARS
            )
            grouped.append(
                GroupedBlock(
                    bbox=bbox,
                    type="header" if is_header else "text",
                    text=text,
                )
            )

    return grouped
