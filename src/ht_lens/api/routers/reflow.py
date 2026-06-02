"""ht_lens 2.0 reflow reading-view API (Phase 8c).

Serves chunk(8a)+translation(8b) as a flowed reading view, plus figure
images and (for the left compare pane) cached source-page renders. All
under ``/v2`` so the 1.x ``/documents`` API + ``viewer.html`` are
untouched (coexist until 8e cutover).

Design (challenge):
- No ``pages`` rows are created — source pages are a **render cache** at
  ``data/extracts_v2/<doc_id>/pages/page_<idx>.png`` (``render_doc_pages``
  populates it once; the endpoint just serves, 404 if absent).
- The v2 image validator accepts ``.png/.jpg/.jpeg`` (MinerU figures are
  ``.jpg`` — a PNG-only guard would break them).
- Each chunk reports ``bbox`` as a 4-number list or ``null`` so the
  viewer does page-level sync always and bbox overlay only when valid
  (two-tier sync).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.api.deps import get_session
from ht_lens.db.models import Chunk, Document
from ht_lens.extract._fitz import open_pdf
from ht_lens.extract.render import render_page_png
from ht_lens.image_repair import (
    IMAGES_FIXED_DIR,
    is_safe_basename,
    load_overrides,
    match_caption_override,
    match_image_override,
)

router = APIRouter(prefix="/v2", tags=["reflow"])

_V2_IMG_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})


def _cache_root() -> Path:
    """Managed-asset root. Overridable via ``HT_LENS_EXTRACTS_V2_DIR`` so
    tests stay hermetic (default matches the 8a ingest dest)."""
    return Path(os.environ.get("HT_LENS_EXTRACTS_V2_DIR", "data/extracts_v2"))


class ReflowChunk(BaseModel):
    id: int
    type: Literal["text", "heading", "equation", "image", "table", "unknown"]
    text_level: int | None
    page_idx: int
    # Reading content: ``translated`` is KO (or LaTeX for equation/passthrough);
    # ``original`` kept for compare/fallback.
    original: str
    translated: str | None
    caption: str | None
    caption_translated: str | None
    img_url: str | None
    bbox: list[float] | None  # 4-number list, or null when provenance absent


class ReflowResponse(BaseModel):
    doc_id: int
    filename: str
    extractor: str
    chunks: list[ReflowChunk]


def _bbox_or_none(bbox_json: str) -> list[float] | None:
    try:
        raw = json.loads(bbox_json)
    except (TypeError, ValueError):
        return None
    if isinstance(raw, list) and len(raw) == 4:
        try:
            return [float(v) for v in raw]
        except (TypeError, ValueError):
            return None
    return None


@router.get("/documents/{doc_id}/reflow", response_model=ReflowResponse)
async def get_reflow(
    doc_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReflowResponse:
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    rows = (
        await session.execute(
            select(Chunk)
            .where(Chunk.doc_id == doc_id)
            .order_by(Chunk.order_idx)
            .options(selectinload(Chunk.translation))
        )
    ).scalars()
    chunks = list(rows)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no chunks for document (not a 2.0/MinerU doc, or not ingested)",
        )
    # Phase 8e-5: non-destructive caption re-assignment (defect 2 — MinerU paired
    # a "Figure N.M" caption to the wrong image on a multi-image page). Applied
    # BEFORE dedup so the corrected captions drive containment (challenge R6).
    overrides = load_overrides(_cache_root() / str(doc_id))
    out: list[ReflowChunk] = []
    for c in chunks:
        tr = c.translation
        # Only surface a translation that actually succeeded; a failed row
        # must not masquerade as content (challenge §5).
        translated = tr.translated_text if (tr and tr.status == "translated") else None
        caption = c.caption
        caption_tr = tr.caption_translated if (tr and tr.status == "translated") else None
        bbox = _bbox_or_none(c.bbox_json)
        cap_ov = match_caption_override(overrides, c.page_idx, c.img_path, bbox)
        if cap_ov is not None:
            # The stored translation is for the OLD (wrong) caption — drop it so
            # the corrected English caption shows without a stale KO mismatch.
            caption = cap_ov.caption
            caption_tr = None
        out.append(
            ReflowChunk(
                id=c.id,
                type=c.type,  # type: ignore[arg-type]
                text_level=c.text_level,
                page_idx=c.page_idx,
                original=c.content,
                translated=translated,
                caption=caption,
                caption_translated=caption_tr,
                img_url=f"/v2/chunks/{c.id}/image" if c.img_path else None,
                bbox=bbox,
            )
        )
    out = _drop_captionless_images_contained_by_captioned(out)
    return ReflowResponse(doc_id=doc_id, filename=doc.filename, extractor=doc.extractor, chunks=out)


def _strict_contains(a: list[float] | None, b: list[float] | None, tol: float = 2.0) -> bool:
    """True if bbox ``a`` strictly encloses ``b`` (covers it within ``tol`` AND
    is strictly larger in area). Malformed/inverted/None bboxes never contain —
    so a bad bbox can't trigger a drop (verify-cross §2.6). Strict-larger keeps
    equal-bbox images (not a nested panel; §3.12)."""
    if a is None or b is None or len(a) != 4 or len(b) != 4:
        return False
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    if ax1 < ax0 or ay1 < ay0 or bx1 < bx0 or by1 < by0:
        return False  # inverted → never contains
    encloses = ax0 - tol <= bx0 and ay0 - tol <= by0 and ax1 + tol >= bx1 and ay1 + tol >= by1
    return encloses and (ax1 - ax0) * (ay1 - ay0) > (bx1 - bx0) * (by1 - by0)


def _drop_captionless_images_contained_by_captioned(
    chunks: list[ReflowChunk],
) -> list[ReflowChunk]:
    """Phase 8e-4: MinerU emits a multi-panel figure as a captioned full-figure
    crop PLUS captionless panel crops nested inside it (doc1 Fig 28.18) — the
    full and panels all render = duplicate. Drop a captionless image ONLY when a
    same-page captioned image strictly contains it. Render-only / non-destructive
    (the DB rows, ``/v2/chunks/{id}/image``, and chat are unaffected). Standalone
    captionless images, equal bboxes, and malformed bboxes are kept."""
    images = [c for c in chunks if c.type == "image"]
    if len(images) < 2:
        return chunks
    by_page: dict[int, list[ReflowChunk]] = {}
    for im in images:
        by_page.setdefault(im.page_idx, []).append(im)
    drop: set[int] = set()
    for page_imgs in by_page.values():
        captioned = [im for im in page_imgs if (im.caption or "").strip()]
        for child in page_imgs:
            if (child.caption or "").strip():
                continue  # only captionless children are drop candidates
            if any(_strict_contains(parent.bbox, child.bbox) for parent in captioned):
                drop.add(child.id)
    if not drop:
        return chunks
    return [c for c in chunks if c.id not in drop]


def _validate_v2_image(raw: str) -> Path:
    """Resolve a managed image path: refuse traversal, allow png/jpg/jpeg."""
    if ".." in Path(raw).parts:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="invalid image path (traversal segment)",
        )
    candidate = Path(raw).resolve()
    if candidate.suffix.lower() not in _V2_IMG_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"image must be one of {sorted(_V2_IMG_SUFFIXES)}",
        )
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found on disk")
    return candidate


_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@router.get("/chunks/{chunk_id}/image")
async def chunk_image(
    chunk_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FileResponse:
    chunk = await session.get(Chunk, chunk_id)
    if chunk is None or not chunk.img_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="chunk image not found")
    # Phase 8e-5: serve the page-clip override (defect 1 — MinerU emitted a
    # degraded black-bg crop) when the manifest matches this chunk by stable
    # evidence. Falls back to the original MinerU file otherwise.
    overrides = load_overrides(_cache_root() / str(chunk.doc_id))
    img_ov = match_image_override(
        overrides, chunk.page_idx, chunk.img_path, _bbox_or_none(chunk.bbox_json)
    )
    if img_ov is not None and is_safe_basename(img_ov.fixed_basename):
        # Defense in depth: load_overrides already drops unsafe basenames, but
        # never join an attacker-controlled value that could escape the root.
        fixed = _cache_root() / str(chunk.doc_id) / IMAGES_FIXED_DIR / img_ov.fixed_basename
        if fixed.is_file():
            path = _validate_v2_image(str(fixed))
            return FileResponse(
                path, media_type=_MEDIA[path.suffix.lower()], headers={"Cache-Control": "no-cache"}
            )
    path = _validate_v2_image(chunk.img_path)
    return FileResponse(
        path, media_type=_MEDIA[path.suffix.lower()], headers={"Cache-Control": "no-cache"}
    )


@router.get("/documents/{doc_id}/page/{page_idx}/image")
async def page_image(
    doc_id: int,
    page_idx: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FileResponse:
    """Serve the cached source-page render for the left compare pane.

    Pages are a render cache (no ``pages`` rows). Missing → 404 (the cache
    is populated out-of-band by ``render_doc_pages``)."""
    if await session.get(Document, doc_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    cache = _cache_root() / str(doc_id) / "pages" / f"page_{page_idx:04d}.png"
    if not cache.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"page render not cached for page_idx={page_idx}",
        )
    return FileResponse(cache, media_type="image/png", headers={"Cache-Control": "no-cache"})


def render_doc_pages(
    doc_id: int, pdf_path: Path, *, dpi: int = 150, dest_root: Path | None = None
) -> int:
    """Render every page of ``pdf_path`` into the doc's page cache.

    Used at 8c working-DB setup (and later by the 8e migration). Returns
    the number of pages rendered. Raises ``FileNotFoundError`` if the
    source PDF is absent (deterministic — never a bogus/empty render)."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"source PDF not found: {pdf_path}")
    dest = (dest_root or _cache_root()) / str(doc_id) / "pages"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    with open_pdf(pdf_path) as doc:
        page_count = doc.page_count  # type: ignore[attr-defined]
        for idx in range(page_count):
            render_page_png(doc, idx, dest / f"page_{idx:04d}.png", dpi=dpi)
            n += 1
    return n


__all__ = ["ReflowChunk", "ReflowResponse", "render_doc_pages", "router"]
