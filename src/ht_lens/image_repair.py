"""Phase 8e-5 — image-repair manifest + page-clip helpers.

Two independent MinerU extraction defects in 2.0 docs are corrected here
**non-destructively** via a per-document ``overrides.json`` manifest — the DB
rows, ``Chunk.img_path`` files, and ingest pipeline are never mutated (same
render-only philosophy as the 8e-4 dedup):

- **Image override** (defect 1): MinerU emits some vector PGM diagrams as a
  black-background raster of just the node blobs (arrows/labels/ellipses lost).
  We re-clip the figure region straight from the source PDF (``*_origin.pdf``)
  and serve that instead.
- **Caption override** (defect 2): on multi-image pages MinerU sometimes pairs
  a "Figure N.M" caption to the wrong image. We re-assign the caption text only
  (the image file is untouched).

Manifest entries are keyed by **stable, content-derived evidence** —
``(page_idx, original img basename, normalized bbox)`` — never by the surrogate
``Chunk.id`` (which a re-ingest can renumber). A serve-time match therefore
re-validates against the current chunk; a stale manifest simply stops matching.

Coordinate basis (verified Phase 8e-5 Stage 0/B across doc1 576x648 + doc5
504x719): ``Chunk.bbox_json`` is the MinerU content_list bbox normalized to a
1000x1000 canvas. The page-point rect is ``bbox/1000 x page.rect`` — confirmed
equal to ``middle.json`` bbox and to the source-PDF ``page.rect``. The math is
verified per page at backfill time (page rect known) so the assumption is never
trusted blindly at serve time.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

# Normalized coords live on a 1000x1000 canvas; allow small MinerU noise.
_NORM_MAX = 1000.0
_NORM_EPS = 5.0
# bbox match tolerance on the 1000-canvas (rounding/re-export drift).
_BBOX_TOL = 2.0

IMAGES_FIXED_DIR = "images_fixed"
OVERRIDES_FILENAME = "overrides.json"


# --------------------------------------------------------------------------- #
# Pure coordinate math
# --------------------------------------------------------------------------- #
def normalized_bbox_to_page_rect(
    bbox_norm: list[float] | None,
    page_w: float,
    page_h: float,
    pad: float = 0.0,
) -> tuple[float, float, float, float] | None:
    """1000-normalized ``bbox_norm`` → page-point rect ``(x0,y0,x1,y1)``.

    Returns ``None`` (caller skips — never a bogus crop) when the bbox is
    malformed, out of the normalized range, or inverted/degenerate. Padding is
    applied in page points and clamped to the page (verify-cross R2 §3)."""
    if bbox_norm is None or len(bbox_norm) != 4 or page_w <= 0 or page_h <= 0:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox_norm)
    except (TypeError, ValueError):
        return None
    if any(v < -_NORM_EPS or v > _NORM_MAX + _NORM_EPS for v in (x0, y0, x1, y1)):
        return None  # not a 1000-normalized bbox → don't guess
    px0, py0 = x0 / _NORM_MAX * page_w, y0 / _NORM_MAX * page_h
    px1, py1 = x1 / _NORM_MAX * page_w, y1 / _NORM_MAX * page_h
    if px1 <= px0 or py1 <= py0:
        return None  # inverted/degenerate
    px0, py0 = max(0.0, px0 - pad), max(0.0, py0 - pad)
    px1, py1 = min(page_w, px1 + pad), min(page_h, py1 + pad)
    if px1 <= px0 or py1 <= py0:
        return None
    return (px0, py0, px1, py1)


# --------------------------------------------------------------------------- #
# Degradation detection (audit aid — NOT the serve-time gate; the repair set is
# a reviewed allowlist captured in the manifest, challenge R1)
# --------------------------------------------------------------------------- #
def black_bg_fraction(path: str | Path, thresh: int = 40, size: int = 64) -> float:
    """Fraction of near-black pixels (luminance < ``thresh``) in a ``size``2
    grayscale downsample. Degraded black-bg diagrams score much higher than normal figures
    (Stage 0: degraded 0.76-0.92 vs normal <=0.45)."""
    from PIL import Image

    with Image.open(path) as im:
        g = im.convert("L").resize((size, size))
        px = list(g.getdata())
    return sum(1 for v in px if v < thresh) / len(px) if px else 0.0


def is_degraded_candidate(path: str | Path, frac_thresh: float = 0.6) -> bool:
    """Black-background heuristic (>0.6). A *candidate* flag for the backfill
    audit only — final repair is the human-reviewed allowlist."""
    try:
        return black_bg_fraction(path) > frac_thresh
    except (OSError, ValueError):
        return False


# --------------------------------------------------------------------------- #
# Manifest model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ImageOverride:
    page_idx: int
    orig_basename: str  # basename of the chunk's MinerU img_path
    bbox: list[float]  # 1000-normalized, stable evidence
    fixed_basename: str  # file under <doc>/images_fixed/

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CaptionOverride:
    page_idx: int
    orig_basename: str
    bbox: list[float]
    caption: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class Overrides:
    images: list[ImageOverride]
    captions: list[CaptionOverride]

    def to_json(self) -> dict[str, object]:
        return {
            "images": [o.to_json() for o in self.images],
            "captions": [o.to_json() for o in self.captions],
        }


def _bbox_close(a: list[float] | None, b: list[float] | None) -> bool:
    if a is None or b is None or len(a) != 4 or len(b) != 4:
        return False
    return all(abs(float(x) - float(y)) <= _BBOX_TOL for x, y in zip(a, b, strict=True))


def overrides_path(doc_root: Path) -> Path:
    return Path(doc_root) / OVERRIDES_FILENAME


def load_overrides(doc_root: Path) -> Overrides:
    """Load ``<doc_root>/overrides.json`` (empty if absent/malformed — a missing
    or broken manifest must never break serving)."""
    p = overrides_path(doc_root)
    if not p.is_file():
        return Overrides(images=[], captions=[])
    try:
        raw = json.loads(p.read_text())
    except (OSError, ValueError):
        return Overrides(images=[], captions=[])
    imgs = [
        ImageOverride(o["page_idx"], o["orig_basename"], o["bbox"], o["fixed_basename"])
        for o in raw.get("images", [])
        if {"page_idx", "orig_basename", "bbox", "fixed_basename"} <= o.keys()
    ]
    caps = [
        CaptionOverride(o["page_idx"], o["orig_basename"], o["bbox"], o["caption"])
        for o in raw.get("captions", [])
        if {"page_idx", "orig_basename", "bbox", "caption"} <= o.keys()
    ]
    return Overrides(images=imgs, captions=caps)


def save_overrides(doc_root: Path, ov: Overrides) -> None:
    doc_root = Path(doc_root)
    doc_root.mkdir(parents=True, exist_ok=True)
    overrides_path(doc_root).write_text(json.dumps(ov.to_json(), indent=2, ensure_ascii=False))


def _basename(img_path: str | None) -> str | None:
    return os.path.basename(img_path) if img_path else None


def match_image_override(
    ov: Overrides, page_idx: int, img_path: str | None, bbox: list[float] | None
) -> ImageOverride | None:
    """Stable-evidence match: same page, same original basename, close bbox.
    A stale entry (basename/bbox no longer match the live chunk) won't match."""
    base = _basename(img_path)
    if base is None:
        return None
    for o in ov.images:
        if o.page_idx == page_idx and o.orig_basename == base and _bbox_close(o.bbox, bbox):
            return o
    return None


def match_caption_override(
    ov: Overrides, page_idx: int, img_path: str | None, bbox: list[float] | None
) -> CaptionOverride | None:
    base = _basename(img_path)
    if base is None:
        return None
    for o in ov.captions:
        if o.page_idx == page_idx and o.orig_basename == base and _bbox_close(o.bbox, bbox):
            return o
    return None


__all__ = [
    "IMAGES_FIXED_DIR",
    "OVERRIDES_FILENAME",
    "CaptionOverride",
    "ImageOverride",
    "Overrides",
    "black_bg_fraction",
    "is_degraded_candidate",
    "load_overrides",
    "match_caption_override",
    "match_image_override",
    "normalized_bbox_to_page_rect",
    "overrides_path",
    "save_overrides",
]
