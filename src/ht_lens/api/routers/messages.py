"""``/threads/{id}/explain`` and ``/threads/{id}/messages`` router — Phase 3.

Transaction order is deliberately ``LLM-call → DB writes`` so a transient LLM
failure never leaves a half-written user row behind.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.api.chat_context import (
    BlockNotFoundError,
    RelatedBlockRef,
    build_block_context_with_refs,
)
from ht_lens.api.deps import (
    get_chat_llm_client,
    get_chat_semaphore,
    get_embedding_client,
    get_session,
)
from ht_lens.api.schemas import MessageCreate, MessageRead, RelatedBlock
from ht_lens.db.models import Message, Thread
from ht_lens.embedding.service import EmbeddingClient
from ht_lens.llm.client import ChatLLMClient
from ht_lens.llm.client import Message as LLMMessage
from ht_lens.llm.errors import LLMError, LLMPermanentError, LLMTransientError

router = APIRouter(prefix="/threads", tags=["messages"])

_EXPLAIN_USER_PROMPT = "위 단락을 자세히 설명해주세요. 핵심 개념, 배경 지식, 관련 용어를 포함해서."

_log = logging.getLogger("ht_lens.api.messages")


async def _load_thread(session: AsyncSession, thread_id: int) -> Thread | None:
    return (
        await session.execute(select(Thread).where(Thread.id == thread_id))
    ).scalar_one_or_none()


async def _thread_history(session: AsyncSession, thread_id: int) -> list[LLMMessage]:
    rows = (
        await session.execute(
            select(Message.role, Message.content)
            .where(Message.thread_id == thread_id)
            .order_by(Message.id.asc())
        )
    ).all()
    history: list[LLMMessage] = []
    for role, content in rows:
        if role == "user":
            history.append({"role": "user", "content": content})
        elif role == "assistant":
            history.append({"role": "assistant", "content": content})
        elif role == "system":
            history.append({"role": "system", "content": content})
    return history


def _llm_model_name(llm: ChatLLMClient) -> str:
    return str(getattr(llm, "model_name", "unknown"))


def _map_llm_error(exc: LLMError) -> HTTPException:
    if isinstance(exc, LLMPermanentError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM permanent error: {exc}",
        )
    if isinstance(exc, LLMTransientError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM transient error: {exc}",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"LLM error: {exc}",
    )


@router.post(
    "/{thread_id}/explain",
    response_model=MessageRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def explain_thread(
    thread_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[ChatLLMClient, Depends(get_chat_llm_client)],
    sem: Annotated[asyncio.Semaphore, Depends(get_chat_semaphore)],
    embedding_client: Annotated[EmbeddingClient | None, Depends(get_embedding_client)],
) -> MessageRead:
    thread = await _load_thread(session, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")

    try:
        block_ctx, refs = await build_block_context_with_refs(
            session,
            thread.block_id,
            radius=2,
            embedding_client=embedding_client,
        )
    except BlockNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    history = await _thread_history(session, thread_id)
    history.append({"role": "user", "content": _EXPLAIN_USER_PROMPT})

    try:
        async with sem:
            assistant_text = await llm.chat(history, system=block_ctx)
    except LLMError as exc:
        _log.warning("explain LLM error thread_id=%s: %s", thread_id, exc)
        raise _map_llm_error(exc) from exc

    now = datetime.utcnow()
    user_msg = Message(
        thread_id=thread_id,
        role="user",
        content=_EXPLAIN_USER_PROMPT,
        model=None,
        created_at=now,
    )
    assistant_msg = Message(
        thread_id=thread_id,
        role="assistant",
        content=assistant_text,
        model=_llm_model_name(llm),
        created_at=now,
    )
    session.add_all([user_msg, assistant_msg])
    await session.commit()
    await session.refresh(assistant_msg)
    response = MessageRead.model_validate(assistant_msg)
    response.related_blocks = _refs_to_schemas(refs)
    return response


@router.post(
    "/{thread_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_message(
    thread_id: int,
    payload: MessageCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[ChatLLMClient, Depends(get_chat_llm_client)],
    sem: Annotated[asyncio.Semaphore, Depends(get_chat_semaphore)],
    embedding_client: Annotated[EmbeddingClient | None, Depends(get_embedding_client)],
) -> MessageRead:
    thread = await _load_thread(session, thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")

    try:
        block_ctx, refs = await build_block_context_with_refs(
            session,
            thread.block_id,
            radius=2,
            embedding_client=embedding_client,
        )
    except BlockNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    history = await _thread_history(session, thread_id)
    history.append({"role": "user", "content": payload.content})

    try:
        async with sem:
            assistant_text = await llm.chat(history, system=block_ctx)
    except LLMError as exc:
        _log.warning("messages LLM error thread_id=%s: %s", thread_id, exc)
        raise _map_llm_error(exc) from exc

    now = datetime.utcnow()
    user_msg = Message(
        thread_id=thread_id,
        role="user",
        content=payload.content,
        model=None,
        created_at=now,
    )
    assistant_msg = Message(
        thread_id=thread_id,
        role="assistant",
        content=assistant_text,
        model=_llm_model_name(llm),
        created_at=now,
    )
    session.add_all([user_msg, assistant_msg])
    await session.commit()
    await session.refresh(assistant_msg)
    response = MessageRead.model_validate(assistant_msg)
    response.related_blocks = _refs_to_schemas(refs)
    return response


def _refs_to_schemas(refs: list[RelatedBlockRef]) -> list[RelatedBlock]:
    """Convert chat_context dataclass refs to API response schema."""
    return [
        RelatedBlock(
            block_id=r.block_id,
            doc_id=r.doc_id,
            doc_filename=r.doc_filename,
            page_num=r.page_num,
            block_local_id=r.block_local_id,
            score=r.score,
            original_preview=r.original_preview,
            translated_preview=r.translated_preview,
        )
        for r in refs
    ]


__all__ = ["router"]
