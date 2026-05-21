"""``/search`` router — Phase 6a.

SQLite LIKE-based cross-document search over block original + translation
text. Preview is built server-side with a single ``<mark>`` tag wrapping the
first match so the client can render via DOMPurify without re-parsing
offsets.
"""

from __future__ import annotations

import html
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.api.deps import get_session
from ht_lens.api.schemas import BlockType, SearchHit
from ht_lens.db.models import Block, Document, Page, Translation

router = APIRouter(tags=["search"])

PREVIEW_RADIUS = 60


def _build_preview(text: str, match_pos: int, match_len: int) -> str:
    """Wrap the matched substring in ``<mark>...</mark>`` and clip to ±radius
    chars with ellipsis. ``text``, ``match_pos``, ``match_len`` come from
    Python str slicing so multibyte characters (e.g. Korean) are handled
    correctly. The non-mark portions are HTML-escaped; the ``<mark>`` is the
    only tag the client ever needs to whitelist."""
    start = max(0, match_pos - PREVIEW_RADIUS)
    end = min(len(text), match_pos + match_len + PREVIEW_RADIUS)
    head = text[start:match_pos]
    matched = text[match_pos : match_pos + match_len]
    tail = text[match_pos + match_len : end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return (
        f"{prefix}{html.escape(head)}<mark>{html.escape(matched)}</mark>{html.escape(tail)}{suffix}"
    )


@router.get("/search", response_model=list[SearchHit])
async def search(
    q: Annotated[str, Query(min_length=2, max_length=200)],
    session: Annotated[AsyncSession, Depends(get_session)],
    doc_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SearchHit]:
    needle = q.strip()
    needle_low = needle.lower()
    pat = f"%{needle_low}%"

    # We rely on SQLite's case-insensitive LIKE for ASCII and lowercase the
    # column ourselves for the few non-ASCII paths the test suite exercises.
    # Sorting: matches in the active document come first, then by page and
    # block order. block_id is the final tie-breaker for determinism.
    stmt = (
        select(
            Block.id.label("block_id"),
            Block.block_local_id,
            Block.type,
            Block.original_text,
            Block.order_idx,
            Page.page_num,
            Document.id.label("doc_id"),
            Document.filename,
            Translation.translated_text,
        )
        .join(Page, Page.id == Block.page_id)
        .join(Document, Document.id == Page.doc_id)
        .outerjoin(Translation, Translation.block_id == Block.id)
        .where((Block.original_text.ilike(pat)) | (Translation.translated_text.ilike(pat)))
        .order_by(
            (Document.id != (doc_id or -1)).asc(),
            Document.id.asc(),
            Page.page_num.asc(),
            Block.order_idx.asc(),
            Block.id.asc(),
        )
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    hits: list[SearchHit] = []
    for row in rows:
        original = row.original_text or ""
        translated = row.translated_text or ""
        # Original takes priority; if it does not match, fall back to the
        # translation field.
        orig_pos = original.lower().find(needle_low)
        matched_field: Literal["original", "translated"]
        if orig_pos >= 0:
            matched_field = "original"
            preview_src = original
            match_pos = orig_pos
        else:
            tr_pos = translated.lower().find(needle_low)
            if tr_pos < 0:
                # SQL matched something we cannot localise (e.g. NULL
                # translation collapsing): skip rather than mislabel.
                continue
            matched_field = "translated"
            preview_src = translated
            match_pos = tr_pos
        preview = _build_preview(preview_src, match_pos, len(needle))
        hits.append(
            SearchHit(
                doc_id=int(row.doc_id),
                doc_filename=str(row.filename),
                page_num=int(row.page_num),
                block_id=int(row.block_id),
                block_local_id=str(row.block_local_id),
                type=cast(BlockType, row.type),
                matched_field=matched_field,
                preview=preview,
            )
        )
    return hits


__all__ = ["router"]
