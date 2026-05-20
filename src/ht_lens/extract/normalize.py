"""Snapshot-friendly normalization for deterministic comparisons."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

REDACTED = "<REDACTED>"
_REDACT_FIELDS_DOC = ("src_pdf_sha256", "extracted_at", "extractor_version")


def round_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (round(bbox[0], 1), round(bbox[1], 1), round(bbox[2], 1), round(bbox[3], 1))


def normalize_page(page_obj: dict[str, Any]) -> dict[str, Any]:
    """Round bboxes to one decimal; preserve structure otherwise."""
    out = deepcopy(page_obj)
    for blk in out.get("blocks", []):
        bbox_seq = tuple(float(v) for v in blk["bbox"])
        if len(bbox_seq) != 4:
            continue
        x0, y0, x1, y1 = bbox_seq
        blk["bbox"] = list(round_bbox((x0, y0, x1, y1)))
    return out


def normalize_doc_meta(meta_obj: dict[str, Any]) -> dict[str, Any]:
    """Redact non-deterministic fields (hash, time, version)."""
    out = deepcopy(meta_obj)
    for field in _REDACT_FIELDS_DOC:
        if field in out:
            out[field] = REDACTED
    return out
