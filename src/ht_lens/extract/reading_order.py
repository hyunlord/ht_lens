"""Reading order resolution.

Phase 1 baseline: trust PyMuPDF ``get_text(sort=True)`` order. Only fall
back to column-aware heuristics when the input ordering is clearly broken
(two or more vertical regressions).
"""

from __future__ import annotations

from ht_lens.extract.blocks import GroupedBlock

_HEADER_WIDTH_RATIO = 0.7
_COLUMN_GAP_RATIO = 0.10
_MAX_COLUMNS = 3
_REGRESSION_THRESHOLD = 2


def _center_x(bbox: tuple[float, float, float, float]) -> float:
    return (bbox[0] + bbox[2]) / 2


def _vertical_regressions(blocks: list[GroupedBlock]) -> int:
    count = 0
    prev_y = -1.0
    for blk in blocks:
        y0 = blk.bbox[1]
        if y0 + 1.0 < prev_y:  # 1pt tolerance
            count += 1
        prev_y = y0
    return count


def _cluster_columns(centers: list[float], page_width: float) -> list[float]:
    """1D agglomerative clustering — returns sorted cluster centers."""
    if not centers:
        return []
    sorted_c = sorted(centers)
    clusters: list[list[float]] = [[sorted_c[0]]]
    gap_threshold = _COLUMN_GAP_RATIO * page_width
    for c in sorted_c[1:]:
        if c - clusters[-1][-1] > gap_threshold:
            clusters.append([c])
        else:
            clusters[-1].append(c)
    if len(clusters) > _MAX_COLUMNS:
        # Merge smallest-gap pairs until we hit the cap.
        merged = clusters
        while len(merged) > _MAX_COLUMNS:
            gaps = [(merged[i + 1][0] - merged[i][-1], i) for i in range(len(merged) - 1)]
            _, idx = min(gaps)
            merged[idx] = merged[idx] + merged[idx + 1]
            merged.pop(idx + 1)
        clusters = merged
    return [sum(c) / len(c) for c in clusters]


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

    centers = [_center_x(b.bbox) for b in body]
    column_centers = _cluster_columns(centers, page_width)
    if len(column_centers) <= 1:
        body.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        return spanning + body

    def _column_index(b: GroupedBlock) -> int:
        cx = _center_x(b.bbox)
        return min(
            range(len(column_centers)),
            key=lambda i: abs(cx - column_centers[i]),
        )

    columns: list[list[GroupedBlock]] = [[] for _ in column_centers]
    for b in body:
        columns[_column_index(b)].append(b)
    for col in columns:
        col.sort(key=lambda b: (b.bbox[1], b.bbox[0]))

    ordered: list[GroupedBlock] = list(spanning)
    for col in columns:
        ordered.extend(col)
    return ordered
