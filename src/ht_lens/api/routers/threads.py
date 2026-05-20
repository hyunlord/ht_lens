"""``/threads`` router — Phase 3."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.api.deps import get_session
from ht_lens.api.schemas import (
    BlockRead,
    MessageRead,
    ThreadCreate,
    ThreadDetail,
    ThreadSummary,
)
from ht_lens.db.models import Block, Message, Page, Thread

router = APIRouter(prefix="/threads", tags=["threads"])


def _block_to_schema(block: Block, *, has_thread: bool) -> BlockRead:
    return BlockRead(
        id=block.id,
        block_local_id=block.block_local_id,
        type=block.type,
        bbox=list(json.loads(block.bbox_json)),
        order=block.order_idx,
        original_text=block.original_text,
        translated_text=block.translation.translated_text if block.translation else None,
        has_thread=has_thread,
    )


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    session: Annotated[AsyncSession, Depends(get_session)],
    doc_id: Annotated[int | None, Query()] = None,
) -> list[ThreadSummary]:
    stmt = (
        select(
            Thread.id,
            Thread.block_id,
            Thread.title,
            Thread.created_at,
            Page.page_num,
            Page.doc_id,
            func.count(Message.id).label("msg_count"),
        )
        .join(Block, Block.id == Thread.block_id)
        .join(Page, Page.id == Block.page_id)
        .outerjoin(Message, Message.thread_id == Thread.id)
        .group_by(Thread.id)
        .order_by(Thread.id.asc())
    )
    if doc_id is not None:
        stmt = stmt.where(Page.doc_id == doc_id)
    rows = (await session.execute(stmt)).all()
    return [
        ThreadSummary(
            id=row.id,
            block_id=row.block_id,
            title=row.title,
            page_num=row.page_num,
            message_count=int(row.msg_count or 0),
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("", response_model=ThreadDetail, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ThreadDetail:
    block = (
        await session.execute(
            select(Block)
            .options(selectinload(Block.page), selectinload(Block.translation))
            .where(Block.id == payload.block_id)
        )
    ).scalar_one_or_none()
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="block not found")

    title = (payload.title or "").strip() or _default_thread_title(block)
    thread = Thread(
        block_id=block.id,
        title=title,
        created_at=datetime.utcnow(),
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    page: Page = block.page
    return ThreadDetail(
        id=thread.id,
        block_id=thread.block_id,
        title=thread.title,
        block=_block_to_schema(block, has_thread=True),
        page_num=page.page_num,
        messages=[],
        created_at=thread.created_at,
    )


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ThreadDetail:
    thread = (
        await session.execute(
            select(Thread)
            .options(
                selectinload(Thread.messages),
                selectinload(Thread.block).selectinload(Block.page),
                selectinload(Thread.block).selectinload(Block.translation),
            )
            .where(Thread.id == thread_id)
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    block = thread.block
    page = block.page
    messages = sorted(thread.messages, key=lambda m: m.id)
    return ThreadDetail(
        id=thread.id,
        block_id=thread.block_id,
        title=thread.title,
        block=_block_to_schema(block, has_thread=True),
        page_num=page.page_num,
        messages=[MessageRead.model_validate(m) for m in messages],
        created_at=thread.created_at,
    )


def _default_thread_title(block: Block) -> str:
    text = (block.original_text or "").strip()
    if not text:
        return f"[빈 {block.type} 블록]"
    snippet = text.splitlines()[0][:60]
    return snippet


__all__ = ["router"]
