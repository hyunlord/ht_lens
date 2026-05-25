"""Block context builder — Phase 3 (+ Phase 7a cross-doc RAG).

Builds a markdown snippet describing a target block plus:
- its ±radius neighbours on the same page (Phase 3)
- top-K vector-similar blocks from *other* documents (Phase 7a)

Sent to the LLM as ``system=`` for ``/explain`` and ``/messages``; never
persisted in the ``messages`` table. The RAG section is best-effort: if
the embedding client is unavailable or the search returns nothing, the
function silently omits it (Codex debate §3: graceful degradation).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.embedding.search import SearchHit, fetch_hit_details, search
from ht_lens.embedding.service import EmbeddingClient


class BlockNotFoundError(LookupError):
    """Raised when ``build_block_context`` receives an unknown block id."""


@dataclass(frozen=True)
class RelatedBlockRef:
    """One cross-doc reference surfaced into chat context.

    Mirrors the API ``RelatedBlock`` schema. Used by routers to attach
    references to the ``/explain`` and ``/messages`` responses so the
    viewer can render the "다른 책의 관련 부분" UI (ROADMAP DoD ④).
    """

    block_id: int
    doc_id: int
    doc_filename: str
    page_num: int
    block_local_id: str
    score: float
    original_preview: str
    translated_preview: str | None


def _default_rag_enabled() -> bool:
    return os.environ.get("RAG_ENABLE_CROSS_DOC", "true").lower() not in (
        "0",
        "false",
        "no",
    )


def _default_rag_top_k() -> int:
    raw = os.environ.get("RAG_TOP_K", "5")
    try:
        return max(0, int(raw))
    except ValueError:
        return 5


def _default_rag_threshold() -> float:
    raw = os.environ.get("RAG_THRESHOLD", "0.5")
    try:
        return float(raw)
    except ValueError:
        return 0.5


def _default_rag_max_chars() -> int:
    raw = os.environ.get("RAG_MAX_CHARS_PER_BLOCK", "200")
    try:
        return max(10, int(raw))
    except ValueError:
        return 200


def _preview(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    t = text.strip().replace("\n", " ")
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def _format_block(
    *,
    page_num: int,
    block: Block,
    translation: Translation | None,
    is_current: bool,
) -> str:
    body = block.original_text.strip()
    if not body:
        body = f"[빈 {block.type} 블록]"
    arrow = "→ " if is_current else "  "
    if translation is not None and translation.translated_text.strip():
        return (
            f"{arrow}[p{page_num} {block.block_local_id} {block.type}] "
            f"{body}\n    번역: {translation.translated_text.strip()}"
        )
    return f"{arrow}[p{page_num} {block.block_local_id} {block.type}] {body}"


async def build_block_context(
    session: AsyncSession,
    block_id: int,
    *,
    radius: int = 2,
    embedding_client: EmbeddingClient | None = None,
    enable_cross_doc: bool | None = None,
    cross_doc_top_k: int | None = None,
    cross_doc_threshold: float | None = None,
    cross_doc_max_chars: int | None = None,
) -> str:
    """Return a markdown block-context for ``block_id`` with ±radius neighbours.

    Phase 7a: when ``embedding_client`` is provided and cross-doc RAG is
    enabled, append a "다른 문서 관련 참조" section with the top-K
    vector-similar blocks from *other* documents. Use
    :func:`build_block_context_with_refs` if the caller also needs the
    structured reference list (for the API response).

    Raises :class:`BlockNotFoundError` if ``block_id`` does not exist.
    Page-boundary neighbours are silently truncated (no cross-page lookup).
    ``radius=0`` omits the neighbourhood section.
    """
    text, _refs = await build_block_context_with_refs(
        session,
        block_id,
        radius=radius,
        embedding_client=embedding_client,
        enable_cross_doc=enable_cross_doc,
        cross_doc_top_k=cross_doc_top_k,
        cross_doc_threshold=cross_doc_threshold,
        cross_doc_max_chars=cross_doc_max_chars,
    )
    return text


async def build_block_context_with_refs(
    session: AsyncSession,
    block_id: int,
    *,
    radius: int = 2,
    embedding_client: EmbeddingClient | None = None,
    enable_cross_doc: bool | None = None,
    cross_doc_top_k: int | None = None,
    cross_doc_threshold: float | None = None,
    cross_doc_max_chars: int | None = None,
) -> tuple[str, list[RelatedBlockRef]]:
    """Same as :func:`build_block_context`, plus the structured references.

    Returns ``(system_text, related_refs)``. ``related_refs`` is empty
    when cross-doc RAG is disabled, the embedding client is unavailable,
    or no hit clears the threshold.
    """
    target = (
        await session.execute(
            select(Block)
            .options(selectinload(Block.page), selectinload(Block.translation))
            .where(Block.id == block_id)
        )
    ).scalar_one_or_none()
    if target is None:
        raise BlockNotFoundError(f"block {block_id} not found")

    page: Page = target.page
    same_page_rows = (
        (
            await session.execute(
                select(Block)
                .options(selectinload(Block.translation))
                .where(Block.page_id == page.id)
                .order_by(Block.order_idx.asc())
            )
        )
        .scalars()
        .all()
    )

    idx = next((i for i, b in enumerate(same_page_rows) if b.id == target.id), None)
    if idx is None:  # pragma: no cover — target must be in its own page
        raise BlockNotFoundError(f"block {block_id} not on its own page")

    target_tr = target.translation
    target_body = target.original_text.strip() or f"[빈 {target.type} 블록]"
    header = [
        f"[Page {page.page_num}, Block {target.block_local_id}]",
        f"원문: {target_body}",
    ]
    if target_tr is not None and target_tr.translated_text.strip():
        header.append(f"번역: {target_tr.translated_text.strip()}")
    else:
        header.append("번역: (번역 없음)")

    parts = ["\n".join(header)]

    if radius > 0:
        lo = max(0, idx - radius)
        hi = min(len(same_page_rows), idx + radius + 1)
        window = same_page_rows[lo:hi]
        ctx_lines = [
            _format_block(
                page_num=page.page_num,
                block=b,
                translation=b.translation,
                is_current=(b.id == target.id),
            )
            for b in window
        ]
        ctx_text = "\n".join(ctx_lines)
        parts.append(f"주변 맥락 (±{radius} blocks):\n{ctx_text}")

    refs: list[RelatedBlockRef] = []
    rag_enabled = enable_cross_doc if enable_cross_doc is not None else _default_rag_enabled()
    if rag_enabled and embedding_client is not None:
        top_k = cross_doc_top_k if cross_doc_top_k is not None else _default_rag_top_k()
        threshold = (
            cross_doc_threshold if cross_doc_threshold is not None else _default_rag_threshold()
        )
        max_chars = (
            cross_doc_max_chars if cross_doc_max_chars is not None else _default_rag_max_chars()
        )
        if top_k > 0:
            refs = await _build_cross_doc_refs(
                session,
                target=target,
                target_doc_id=page.doc_id,
                embedding_client=embedding_client,
                top_k=top_k,
                threshold=threshold,
                max_chars=max_chars,
            )
            if refs:
                parts.append(_render_cross_doc_section(refs))

    parts.append("---")
    return "\n\n".join(parts), refs


async def _build_cross_doc_refs(
    session: AsyncSession,
    *,
    target: Block,
    target_doc_id: int,
    embedding_client: EmbeddingClient,
    top_k: int,
    threshold: float,
    max_chars: int,
) -> list[RelatedBlockRef]:
    """Run vector search + resolve preview metadata into ``RelatedBlockRef``."""
    text = (target.original_text or "").strip()
    if not text:
        return []
    query_vec = embedding_client.encode([text])[0]
    hits: list[SearchHit] = await search(
        session,
        query_vector=query_vec,
        top_k=top_k,
        threshold=threshold,
        exclude_doc_ids={target_doc_id},
        exclude_block_ids={target.id},
    )
    if not hits:
        return []
    details = await fetch_hit_details(session, hits)
    # Resolve filenames in one query.
    doc_ids = {h.doc_id for h in hits}
    doc_rows = (
        await session.execute(
            select(Document.id, Document.filename).where(Document.id.in_(doc_ids))
        )
    ).all()
    filenames = {did: name for did, name in doc_rows}

    refs: list[RelatedBlockRef] = []
    for hit in hits:
        d = details.get(hit.block_id)
        if d is None:
            continue
        blk, page, tr = d
        refs.append(
            RelatedBlockRef(
                block_id=blk.id,
                doc_id=hit.doc_id,
                doc_filename=filenames.get(hit.doc_id, ""),
                page_num=page.page_num,
                block_local_id=blk.block_local_id,
                score=hit.score,
                original_preview=_preview(blk.original_text, max_chars),
                translated_preview=(
                    _preview(tr.translated_text, max_chars)
                    if tr is not None and tr.translated_text
                    else None
                ),
            )
        )
    return refs


def _render_cross_doc_section(refs: list[RelatedBlockRef]) -> str:
    """Format the cross-doc references for the chat system message."""
    lines = ["다른 문서 관련 참조 (top-K):"]
    for r in refs:
        head = f"[{r.doc_filename} p.{r.page_num} {r.block_local_id} score={r.score:.2f}]"
        body = r.original_preview
        if r.translated_preview:
            body = f"{body} → {r.translated_preview}"
        lines.append(f"  {head} {body}")
    return "\n".join(lines)


__all__ = [
    "BlockNotFoundError",
    "RelatedBlockRef",
    "build_block_context",
    "build_block_context_with_refs",
]
