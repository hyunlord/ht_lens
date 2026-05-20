"""``/documents/{doc_id}/pages/{page_num}`` router — Phase 3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.api.deps import get_session
from ht_lens.api.schemas import BlockRead, PageRead, PageRender
from ht_lens.db.models import Block, Document, Page, Thread

router = APIRouter(prefix="/documents", tags=["pages"])

_PNG_CACHE_HEADER = "public, max-age=2592000"


async def _load_page(session: AsyncSession, doc_id: int, page_num: int) -> Page | None:
    stmt = (
        select(Page)
        .options(selectinload(Page.blocks).selectinload(Block.translation))
        .where(Page.doc_id == doc_id, Page.page_num == page_num)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _doc_exists(session: AsyncSession, doc_id: int) -> bool:
    res = await session.execute(select(Document.id).where(Document.id == doc_id))
    return res.scalar_one_or_none() is not None


@router.get("/{doc_id}/pages/{page_num}", response_model=PageRead)
async def get_page(
    doc_id: int,
    page_num: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PageRead:
    if not await _doc_exists(session, doc_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    page = await _load_page(session, doc_id, page_num)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page not found")

    block_ids = [b.id for b in page.blocks]
    thread_block_ids: set[int] = set()
    if block_ids:
        rows = await session.execute(select(Thread.block_id).where(Thread.block_id.in_(block_ids)))
        thread_block_ids = {row[0] for row in rows.all()}

    blocks = [
        BlockRead(
            id=b.id,
            block_local_id=b.block_local_id,
            type=b.type,
            bbox=list(json.loads(b.bbox_json)),
            order=b.order_idx,
            original_text=b.original_text,
            translated_text=b.translation.translated_text if b.translation else None,
            has_thread=b.id in thread_block_ids,
        )
        for b in page.blocks
    ]
    scale = page.pixel_width / page.width if page.width else 1.0
    return PageRead(
        page_num=page.page_num,
        width=page.width,
        height=page.height,
        rotation=page.rotation,
        render=PageRender(
            dpi=page.render_dpi,
            pixel_w=page.pixel_width,
            pixel_h=page.pixel_height,
            scale=scale,
        ),
        blocks=blocks,
    )


def _validate_image_path(raw: str) -> Path:
    """Return a usable absolute path or raise ``HTTPException(500)``.

    Trust boundary: ``bg_image_path`` is set by ``ht-lens ingest`` (operator).
    We still refuse traversal segments and non-png extensions defensively.
    """
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


@router.get("/{doc_id}/pages/{page_num}/image")
async def get_page_image(
    doc_id: int,
    page_num: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FileResponse:
    if not await _doc_exists(session, doc_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    stmt = select(Page.bg_image_path).where(Page.doc_id == doc_id, Page.page_num == page_num)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page not found")
    path = _validate_image_path(row)
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": _PNG_CACHE_HEADER},
    )


__all__ = ["router"]
