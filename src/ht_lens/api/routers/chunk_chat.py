"""ht_lens 2.0 chunk chat router (Phase 8d-2a) — ``/v2/threads`` + ``/v2/pins``.

Paragraph (chunk) and section chat over the 2.0 chunk schema, persisted in
the new ``chunk_threads``/``chunk_messages`` tables (1.x ``threads`` untouched).
Mirrors the 1.x ``messages.py`` contract: **LLM-call → DB-write** so a
transient LLM failure never persists a half-written turn (challenge R8). A
section anchor stores the section's HEADING ``chunk_id`` (challenge R1).
RAG/figure/neighbour-retranslate are 8d-2b.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.api.chunk_chat_context import (
    ChatContext,
    build_chunk_context,
    build_section_context,
)
from ht_lens.api.deps import get_chat_llm_client, get_chat_semaphore, get_session
from ht_lens.api.schemas import (
    ChunkMessageCreate,
    ChunkMessageRead,
    ChunkPinCreate,
    ChunkPinRead,
    ChunkThreadCreate,
    ChunkThreadRead,
    ChunkThreadSummary,
)
from ht_lens.db.models import Chunk, ChunkMessage, ChunkPin, ChunkThread
from ht_lens.llm.client import ChatLLMClient
from ht_lens.llm.client import Message as LLMMessage
from ht_lens.llm.errors import LLMError, LLMPermanentError, LLMTransientError

router = APIRouter(prefix="/v2", tags=["chunk-chat"])
_log = logging.getLogger("ht_lens.api.chunk_chat")

_SYSTEM_PREAMBLE = (
    "당신은 학술 번역본 읽기를 돕는 조교입니다. 아래 문맥(원문/번역)을 근거로 "
    "한국어로 정확히 답하세요. 문맥에 없으면 모른다고 하세요.\n\n"
)


def _map_llm_error(exc: LLMError) -> HTTPException:
    detail = (
        f"LLM permanent error: {exc}"
        if isinstance(exc, LLMPermanentError)
        else f"LLM transient error: {exc}"
        if isinstance(exc, LLMTransientError)
        else f"LLM error: {exc}"
    )
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


def _preview(text: str, n: int = 60) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[: n - 1] + "…" if len(t) > n else t


async def _load_anchor_chunk(session: AsyncSession, doc_id: int, chunk_id: int) -> Chunk:
    """Resolve the anchor chunk + enforce it belongs to ``doc_id`` (challenge R4)."""
    chunk = await session.get(Chunk, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="anchor chunk not found")
    if chunk.doc_id != doc_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="anchor chunk does not belong to doc_id",
        )
    return chunk


@router.post("/threads", response_model=ChunkThreadRead, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ChunkThreadCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChunkThread:
    chunk = await _load_anchor_chunk(session, payload.doc_id, payload.chunk_id)
    if payload.anchor_type == "section" and chunk.type != "heading":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="section anchor must reference a heading chunk",
        )
    title = payload.title or _preview(chunk.content) or f"chunk {chunk.id}"
    thread = ChunkThread(
        doc_id=payload.doc_id,
        anchor_type=payload.anchor_type,
        chunk_id=payload.chunk_id,
        title=title,
        created_at=datetime.utcnow(),
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


@router.get("/documents/{doc_id}/threads", response_model=list[ChunkThreadSummary])
async def list_threads(
    doc_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ChunkThreadSummary]:
    rows = (
        await session.execute(
            select(
                ChunkThread,
                func.count(ChunkMessage.id),
            )
            .outerjoin(ChunkMessage, ChunkMessage.thread_id == ChunkThread.id)
            .where(ChunkThread.doc_id == doc_id)
            .group_by(ChunkThread.id)
            .order_by(ChunkThread.id.desc())
        )
    ).all()
    return [
        ChunkThreadSummary(
            id=t.id,
            doc_id=t.doc_id,
            anchor_type=t.anchor_type,
            chunk_id=t.chunk_id,
            title=t.title,
            message_count=count,
            created_at=t.created_at,
        )
        for t, count in rows
    ]


@router.get("/threads/{thread_id}/messages", response_model=list[ChunkMessageRead])
async def get_messages(
    thread_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ChunkMessage]:
    if await session.get(ChunkThread, thread_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    rows = (
        await session.execute(
            select(ChunkMessage)
            .where(ChunkMessage.thread_id == thread_id)
            .order_by(ChunkMessage.id.asc())
        )
    ).scalars()
    return list(rows)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await session.execute(delete(ChunkThread).where(ChunkThread.id == thread_id))
    await session.commit()


async def _build_context(session: AsyncSession, thread: ChunkThread) -> ChatContext:
    if thread.anchor_type == "section":
        return await build_section_context(session, thread.doc_id, thread.chunk_id)
    return await build_chunk_context(session, thread.chunk_id)


@router.post(
    "/threads/{thread_id}/messages",
    response_model=ChunkMessageRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_message(
    thread_id: int,
    payload: ChunkMessageCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[ChatLLMClient, Depends(get_chat_llm_client)],
    sem: Annotated[asyncio.Semaphore, Depends(get_chat_semaphore)],
) -> ChunkMessage:
    thread = await session.get(ChunkThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")

    ctx = await _build_context(session, thread)
    prior = (
        await session.execute(
            select(ChunkMessage)
            .where(ChunkMessage.thread_id == thread_id)
            .order_by(ChunkMessage.id.asc())
        )
    ).scalars()
    history: list[LLMMessage] = []
    for m in prior:  # explicit role narrowing keeps the TypedDict literal (mypy)
        if m.role == "user":
            history.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            history.append({"role": "assistant", "content": m.content})
        elif m.role == "system":
            history.append({"role": "system", "content": m.content})
    history.append({"role": "user", "content": payload.content})

    try:
        async with sem:
            assistant_text = await llm.chat(history, system=_SYSTEM_PREAMBLE + ctx.text)
    except LLMError as exc:
        _log.warning("chunk-chat LLM error thread_id=%s: %s", thread_id, exc)
        raise _map_llm_error(exc) from exc  # nothing written yet (challenge R8)

    # A DELETE during the LLM call must not orphan messages (challenge R8).
    # Drop the pre-LLM read snapshot so the re-fetch sees committed deletes;
    # the FK on chunk_messages.thread_id is the hard backstop at commit.
    await session.rollback()
    if await session.get(ChunkThread, thread_id) is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="thread was deleted during the request",
        )

    now = datetime.utcnow()
    session.add(
        ChunkMessage(
            thread_id=thread_id, role="user", content=payload.content, model=None, created_at=now
        )
    )
    assistant = ChunkMessage(
        thread_id=thread_id,
        role="assistant",
        content=assistant_text,
        model=str(getattr(llm, "model_name", "unknown")),
        created_at=now,
    )
    session.add(assistant)
    try:
        await session.commit()
    except IntegrityError as exc:  # FK backstop: parent vanished mid-flight
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="thread was deleted during the request",
        ) from exc
    await session.refresh(assistant)
    return assistant


@router.post("/pins", response_model=ChunkPinRead, status_code=status.HTTP_201_CREATED)
async def create_pin(
    payload: ChunkPinCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChunkPin:
    await _load_anchor_chunk(session, payload.doc_id, payload.chunk_id)
    pin = ChunkPin(doc_id=payload.doc_id, chunk_id=payload.chunk_id, created_at=datetime.utcnow())
    session.add(pin)
    await session.commit()
    await session.refresh(pin)
    return pin


@router.get("/documents/{doc_id}/pins", response_model=list[ChunkPinRead])
async def list_pins(
    doc_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ChunkPin]:
    rows = (
        await session.execute(
            select(ChunkPin).where(ChunkPin.doc_id == doc_id).order_by(ChunkPin.id.desc())
        )
    ).scalars()
    return list(rows)


@router.delete("/pins/{pin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pin(
    pin_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    await session.execute(delete(ChunkPin).where(ChunkPin.id == pin_id))
    await session.commit()


__all__ = ["router"]
