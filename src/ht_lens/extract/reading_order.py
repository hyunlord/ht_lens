"""Reading order resolution.

Phase 1 baseline: trust PyMuPDF ``get_text(sort=True)`` order. When that
order regresses vertically — which can happen on cover pages with rotated
margin text or on layouts that PyMuPDF misorders — fall back to a simple
y0 sort with page-spanning headers lifted to the top.

Aggressive column detection was tried and abandoned for Phase 1: on the
arXiv cover fixture, single-block marginalia (vertical stamps) plus a few
isolated labels generated spurious "columns" that scrambled the order
worse than no fallback at all. ROADMAP Phase 1 targets only 80%; we
intentionally keep the fallback humble.
"""

from __future__ import annotations

from ht_lens.extract.blocks import GroupedBlock

_HEADER_WIDTH_RATIO = 0.7
_REGRESSION_THRESHOLD = 1  # any backward jump in y triggers fallback


def _vertical_regressions(blocks: list[GroupedBlock]) -> int:
    count = 0
    prev_y = -1.0
    for blk in blocks:
        y0 = blk.bbox[1]
        if y0 + 1.0 < prev_y:  # 1pt tolerance
            count += 1
        prev_y = y0
    return count


def order_blocks(blocks: list[GroupedBlock], page_width: float) -> list[GroupedBlock]:
    """Return ``blocks`` in reading order."""
    if len(blocks) <= 1:
        return list(blocks)

    if _vertical_regressions(blocks) < _REGRESSION_THRESHOLD:
        return list(blocks)

    spanning: list[GroupedBlock] = []
    body: list[GroupedBlock] = []
    for blk in blocks:
        width = blk.bbox[2] - blk.bbox[0]
        if width >= _HEADER_WIDTH_RATIO * page_width:
            spanning.append(blk)
        else:
            body.append(blk)

    spanning.sort(key=lambda b: b.bbox[1])
    body.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    return spanning + body
