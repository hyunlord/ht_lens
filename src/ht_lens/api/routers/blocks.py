"""``/blocks/{id}/retranslate`` router — Phase 6a.

Forces a fresh translation for a single block (text or header). On success
the existing ``translations`` row is upserted with the new text + cache key.
LLM call happens BEFORE any DB write so a transient failure leaves no
partial row behind (Phase 3 atomicity pattern).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.api.deps import (
    get_chat_semaphore,
    get_embedding_client,
    get_session,
    get_translate_llm_client,
)
from ht_lens.api.schemas import RelatedBlock, RetranslateResponse, TranslationRead
from ht_lens.db.models import Block, Document, Translation
from ht_lens.embedding.lookup import get_or_encode_block_vector
from ht_lens.embedding.search import fetch_hit_details, search
from ht_lens.embedding.service import EmbeddingClient
from ht_lens.llm.client import TranslateLLMClient
from ht_lens.llm.errors import LLMError, LLMPermanentError, LLMTransientError
from ht_lens.translate.cache import cache_key as make_cache_key

router = APIRouter(prefix="/blocks", tags=["blocks"])

_RETRANSLATABLE_TYPES = ("text", "header")
_log = logging.getLogger("ht_lens.api.blocks")


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
    "/{block_id}/retranslate",
    response_model=RetranslateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retranslate_block(
    block_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[TranslateLLMClient, Depends(get_translate_llm_client)],
    sem: Annotated[asyncio.Semaphore, Depends(get_chat_semaphore)],
) -> RetranslateResponse:
    block = (
        await session.execute(
            select(Block).options(selectinload(Block.page)).where(Block.id == block_id)
        )
    ).scalar_one_or_none()
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="block not found")
    if block.type not in _RETRANSLATABLE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"block type {block.type!r} cannot be retranslated",
        )

    doc = await session.get(Document, block.page.doc_id)
    if doc is None:
        # Should never happen — block.page joinedloaded — but stay defensive.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    try:
        async with sem:
            new_text = await llm.translate(block.original_text, doc.src_lang, doc.tgt_lang)
    except LLMError as exc:
        _log.warning("retranslate LLM error block_id=%s: %s", block_id, exc)
        raise _map_llm_error(exc) from exc

    # R1 fix: manual retranslate must NOT pollute the global cache. The
    # translate pipeline (Phase 2b) looks up translations by ``cache_key``,
    # so reusing the same key after a manual retranslate could leak the
    # override into sibling blocks with identical ``original_text``. Instead:
    #   - tag ``model`` with a ``manual-retranslate:`` prefix so provenance
    #     is preserved
    #   - set ``cache_key = None`` so the cache lookup in
    #     ``translate/pipeline.py::_db_cache_lookup`` skips this row
    base_model = str(getattr(llm, "model_name", "unknown"))
    now = datetime.now(UTC)
    model = f"manual-retranslate:{base_model}:{int(now.timestamp())}"
    # Compute the would-be key only for forensic logging; never store it.
    _ = make_cache_key(block.original_text, doc.src_lang, doc.tgt_lang, base_model)

    existing = await session.get(Translation, block_id)
    if existing is None:
        translation = Translation(
            block_id=block_id,
            translated_text=new_text,
            model=model,
            cache_key=None,
            status="translated",
            updated_at=now,
        )
        session.add(translation)
    else:
        existing.translated_text = new_text
        existing.model = model
        existing.cache_key = None
        existing.status = "translated"
        existing.updated_at = now
        translation = existing
    await session.commit()
    await session.refresh(translation)
    return RetranslateResponse(
        block_id=block_id,
        translation=TranslationRead.model_validate(translation),
    )


@router.get("/{block_id}/related", response_model=list[RelatedBlock])
async def related_blocks(
    block_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    embedding_client: Annotated[EmbeddingClient | None, Depends(get_embedding_client)],
    k: int = 5,
    threshold: float = 0.5,
) -> list[RelatedBlock]:
    """Phase 7a — list cross-doc vector-similar blocks for a target block.

    Returns up to ``k`` results with score ≥ ``threshold``, excluding the
    target block's own document. ``503`` when the embedding subsystem is
    unavailable (model load failed at startup, ``RAG_DISABLED=1``).
    """
    if embedding_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedding subsystem unavailable",
        )
    if k <= 0 or k > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="k must be between 1 and 50",
        )

    target = (
        await session.execute(
            select(Block).options(selectinload(Block.page)).where(Block.id == block_id)
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="block not found")

    text = (target.original_text or "").strip()
    if not text:
        return []
    # Phase 7a-2: reuse the stored block_embeddings vector when fresh; falls
    # back to encode() when the row is missing or source_hash is stale.
    query_vec = await get_or_encode_block_vector(session, embedding_client, target)
    hits = await search(
        session,
        query_vector=query_vec,
        top_k=k,
        threshold=threshold,
        exclude_doc_ids={target.page.doc_id},
        exclude_block_ids={target.id},
    )
    if not hits:
        return []
    details = await fetch_hit_details(session, hits)
    doc_ids = {h.doc_id for h in hits}
    filenames = {
        did: name
        for did, name in (
            await session.execute(
                select(Document.id, Document.filename).where(Document.id.in_(doc_ids))
            )
        ).all()
    }
    out: list[RelatedBlock] = []
    for hit in hits:
        d = details.get(hit.block_id)
        if d is None:
            continue
        blk, page, tr = d
        out.append(
            RelatedBlock(
                block_id=blk.id,
                doc_id=hit.doc_id,
                doc_filename=filenames.get(hit.doc_id, ""),
                page_num=page.page_num,
                block_local_id=blk.block_local_id,
                score=hit.score,
                original_preview=(blk.original_text or "").strip()[:200],
                translated_preview=((tr.translated_text or "").strip()[:200] if tr else None),
            )
        )
    return out


__all__ = ["router"]
