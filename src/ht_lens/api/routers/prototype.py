"""Throwaway reflow-reading-mode prototype (NOT a Phase).

Two endpoints used only by ``static/prototype_reflow.html`` to validate
whether a flowed-text reading view (left: PDF original, right: KO reflow)
beats the bbox-overlay viewer for textbook-style content.

- ``GET /prototype/documents/{doc_id}/reflow?start_page&end_page``
  Returns blocks ordered (page_num, order_idx) with text + crop URL.
- ``GET /prototype/blocks/{block_id}/crop[?scale=]``
  PNG-crops an image block's bbox out of the cached page render.

This module is intentionally outside the normal /documents tree so the
existing API contract stays stable; nothing in production depends on it.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.api.deps import get_session
from ht_lens.db.models import Block, Page

router = APIRouter(prefix="/prototype", tags=["prototype"])

_MAX_PAGE_RANGE = 30  # safety cap; chapters in book2 fit easily


class ReflowBlock(BaseModel):
    """Single reflow item — text/header carry ``translated``; image carries ``crop_url``."""

    id: int
    page: int
    order: int
    type: Literal["text", "header", "image"]
    original: str | None = None
    translated: str | None = None
    crop_url: str | None = None
    bbox: list[float]


class ReflowResponse(BaseModel):
    doc_id: int
    start_page: int
    end_page: int
    blocks: list[ReflowBlock]


@router.get("/documents/{doc_id}/reflow", response_model=ReflowResponse)
async def get_reflow(
    doc_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    start_page: Annotated[int, Query(ge=1)],
    end_page: Annotated[int, Query(ge=1)],
) -> ReflowResponse:
    if end_page < start_page:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_page must be >= start_page",
        )
    if end_page - start_page + 1 > _MAX_PAGE_RANGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"reflow range capped at {_MAX_PAGE_RANGE} pages",
        )

    stmt = (
        select(Page)
        .options(selectinload(Page.blocks).selectinload(Block.translation))
        .where(
            Page.doc_id == doc_id,
            Page.page_num >= start_page,
            Page.page_num <= end_page,
        )
        .order_by(Page.page_num)
    )
    pages = list((await session.execute(stmt)).scalars())
    if not pages:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no pages found in range (document may not exist)",
        )

    blocks: list[ReflowBlock] = []
    for page in pages:
        for b in sorted(page.blocks, key=lambda x: x.order_idx):
            bbox = list(json.loads(b.bbox_json))
            if b.type == "image":
                blocks.append(
                    ReflowBlock(
                        id=b.id,
                        page=page.page_num,
                        order=b.order_idx,
                        type="image",
                        crop_url=f"/prototype/blocks/{b.id}/crop",
                        bbox=bbox,
                    )
                )
            else:
                blocks.append(
                    ReflowBlock(
                        id=b.id,
                        page=page.page_num,
                        order=b.order_idx,
                        # The data model only stores "text" / "header" / "image";
                        # passthrough whichever the extractor labelled.
                        type="header" if b.type == "header" else "text",
                        original=b.original_text,
                        translated=b.translation.translated_text if b.translation else None,
                        bbox=bbox,
                    )
                )
    return ReflowResponse(
        doc_id=doc_id,
        start_page=start_page,
        end_page=end_page,
        blocks=blocks,
    )


def _validate_png_path(raw: str) -> Path:
    """Same trust posture as ``pages._validate_image_path`` — refuses
    traversal segments and non-png extensions."""
    if ".." in Path(raw).parts:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="invalid bg_image_path (traversal segment)",
        )
    candidate = Path(raw).resolve()
    if candidate.suffix.lower() != ".png":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="bg_image_path must be .png",
        )
    if not candidate.is_file():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="bg_image_path does not exist on disk",
        )
    return candidate


@router.get("/blocks/{block_id}/crop")
async def crop_image_block(
    block_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Crop an ``image`` block's bbox out of the rendered page PNG.

    The block's bbox is in PDF points (page.width / page.height units);
    the cached PNG is rendered at ``page.render_dpi``. We use the stored
    ``pixel_width / page.width`` ratio (which already accounts for any
    rounding the renderer applied) instead of recomputing from dpi.
    """
    stmt = select(Block, Page).join(Page, Page.id == Block.page_id).where(Block.id == block_id)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="block not found")
    block, page = row
    if block.type != "image":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="crop is only meaningful for image blocks",
        )

    bbox = json.loads(block.bbox_json)
    if not (isinstance(bbox, list) and len(bbox) == 4):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="malformed bbox_json",
        )
    x0, y0, x1, y1 = (float(v) for v in bbox)
    if x1 <= x0 or y1 <= y0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="non-positive bbox",
        )

    sx = page.pixel_width / page.width if page.width else 1.0
    sy = page.pixel_height / page.height if page.height else 1.0
    px0 = max(0, round(x0 * sx))
    py0 = max(0, round(y0 * sy))
    px1 = min(page.pixel_width, round(x1 * sx))
    py1 = min(page.pixel_height, round(y1 * sy))
    if px1 <= px0 or py1 <= py0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="bbox collapsed to zero area after scaling",
        )

    path = _validate_png_path(page.bg_image_path)
    with Image.open(path) as im:
        cropped = im.crop((px0, py0, px1, py1))
        buf = io.BytesIO()
        cropped.save(buf, format="PNG", optimize=True)
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


__all__ = ["router"]
