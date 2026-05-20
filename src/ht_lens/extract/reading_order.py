"""Reading order resolution.

Phase 1 baseline: trust PyMuPDF ``get_text(sort=True)`` order. When that
order regresses vertically — which happens on cover pages with rotated
margin text, on layouts that PyMuPDF misorders, or when wide body
paragraphs precede taller-y narrow headers in the emitted order — fall
back to a plain top-to-bottom ``(y0, x0)`` sort.

Earlier RE-CODE rounds added a "spanning header lift" that pulled any
block wider than 70% of the page above the rest. That heuristic produced
a real defect on ``sample_ko.pdf`` (wide single-column body paragraphs
got lifted ahead of narrow top-of-page intros and images), so the lift
was removed. ROADMAP Phase 1 targets 80%; we keep the fallback minimal.
"""

from __future__ import annotations

from ht_lens.extract.blocks import GroupedBlock

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


def order_blocks(blocks: list[GroupedBlock]) -> list[GroupedBlock]:
    """Return ``blocks`` in reading order."""
    if len(blocks) <= 1:
        return list(blocks)

    if _vertical_regressions(blocks) < _REGRESSION_THRESHOLD:
        return list(blocks)

    return sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))
