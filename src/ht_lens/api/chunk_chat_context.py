"""Chunk chat context builder — Phase 8d-2a.

Builds the LLM ``system=`` context for two anchor modes:
- paragraph (``build_chunk_context``): target chunk + ±radius neighbours in
  document order (reflow is continuous across pages).
- section (``build_section_context``): all chunks of the section beginning
  at a HEADING chunk, bounded by dotted-secNo depth (challenge R1 — anchored
  by heading_chunk_id, not the ambiguous sec_no). Large sections are an
  explicit DEGRADED state: heading + budget-fit chunks + a notice; relevance
  top-K is deferred to 8d-2b.

RAG-free (cross-doc + within-section top-K = 8d-2b). Returns a typed object
exposing exactly what the model saw (challenge R7). Translated text is used
when the translation succeeded, else the original, each labelled by type
(challenge R6) so the prompt is never an unlabelled KO/EN/LaTeX mix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Chunk, Document
from ht_lens.embedding.chunk_search import fetch_chunk_hit_details, search_chunks

_SEC_RE = re.compile(r"^\s*§?\s*(\d+(?:\.\d+)*)\.?(?=\s|$)")
_TYPE_LABEL = {
    "heading": "섹션",
    "text": "본문",
    "equation": "수식",
    "image": "그림",
    "table": "표",
}
_DEFAULT_SECTION_BUDGET = 6000


class ChunkNotFoundError(LookupError):
    """Raised when a context builder receives an unknown chunk / heading id."""


@dataclass
class ChatContext:
    """What the model actually saw — lets tests assert the prompt, not just
    that a response was persisted (challenge R7)."""

    text: str
    included_chunk_ids: list[int] = field(default_factory=list)
    truncated: bool = False
    total_chunks: int = 0
    # Representative text for the cross-doc query (challenge R4): for a figure
    # this is caption+neighbours, NOT the image chunk's empty content.
    query_text: str = ""


@dataclass(frozen=True)
class RelatedChunkRef:
    """One cross-doc chunk reference surfaced into chat context + the API
    response (challenge R3, mirrors RelatedBlockRef)."""

    chunk_id: int
    doc_id: int
    doc_filename: str
    page_idx: int
    score: float
    original_preview: str
    translated_preview: str | None


def parse_section_no(text: str | None) -> str | None:
    """Leading dotted section number ("28.4.2 Title" -> "28.4.2"), else None.
    Python port of sections.js parseSectionNo (8d-1) — kept in parity by
    ``tests/integration/test_chunk_chat_context.py``."""
    if not text:
        return None
    m = _SEC_RE.match(text)
    return m.group(1) if m else None


def _depth(sec_no: str) -> int:
    return len(sec_no.split("."))


def _label(chunk: Chunk) -> str:
    return _TYPE_LABEL.get(chunk.type, chunk.type)


def _body(chunk: Chunk) -> str:
    """Translated text when the translation succeeded, else the original
    (failed/absent translations fall back to source — challenge R6)."""
    tr = chunk.translation
    if tr is not None and tr.status == "translated" and (tr.translated_text or "").strip():
        return tr.translated_text.strip()
    return (chunk.content or "").strip()


def _render(chunk: Chunk, *, current: bool = False) -> str:
    arrow = "→ " if current else "  "
    return f"{arrow}[{_label(chunk)}] {_body(chunk) or f'[빈 {_label(chunk)}]'}"


async def _doc_chunks(session: AsyncSession, doc_id: int) -> list[Chunk]:
    rows = (
        await session.execute(
            select(Chunk)
            .where(Chunk.doc_id == doc_id)
            .order_by(Chunk.order_idx)
            .options(selectinload(Chunk.translation))
        )
    ).scalars()
    return list(rows)


async def build_chunk_context(
    session: AsyncSession, chunk_id: int, *, radius: int = 2
) -> ChatContext:
    """Paragraph context: target chunk + ±radius neighbours (document order,
    crossing page boundaries since reflow is continuous). RAG refs = 8d-2b."""
    target = (
        await session.execute(
            select(Chunk).where(Chunk.id == chunk_id).options(selectinload(Chunk.translation))
        )
    ).scalar_one_or_none()
    if target is None:
        raise ChunkNotFoundError(f"chunk {chunk_id} not found")
    chunks = await _doc_chunks(session, target.doc_id)
    idx = next((i for i, c in enumerate(chunks) if c.id == target.id), None)
    if idx is None:  # pragma: no cover — target is in its own document
        raise ChunkNotFoundError(f"chunk {chunk_id} not in its own document")
    lo = max(0, idx - radius)
    hi = min(len(chunks), idx + radius + 1)
    window = chunks[lo:hi]
    header = f"[현재 문단] {_body(target) or '[빈 문단]'}"
    ctx = "\n".join(_render(c, current=(c.id == target.id)) for c in window)
    return ChatContext(
        text=f"{header}\n\n주변 맥락 (±{radius}):\n{ctx}\n---",
        included_chunk_ids=[c.id for c in window],
        truncated=False,
        total_chunks=len(window),
    )


def section_chunk_range(chunks: list[Chunk], heading_chunk_id: int) -> list[Chunk]:
    """Chunks of the section starting at ``heading_chunk_id``: from that
    heading until the next heading of same-or-shallower dotted depth (a
    parent includes its children — challenge R1). An unnumbered heading
    stops at the next heading of any kind (fallback). ``chunks`` must be in
    document order."""
    head = next((i for i, c in enumerate(chunks) if c.id == heading_chunk_id), None)
    if head is None:
        return []
    start_sec = parse_section_no(chunks[head].content)
    start_depth = _depth(start_sec) if start_sec else None
    end = len(chunks)
    for j in range(head + 1, len(chunks)):
        c = chunks[j]
        if c.type != "heading":
            continue
        if start_depth is None:
            end = j  # unnumbered heading: stop at the next heading of any kind
            break
        sn = parse_section_no(c.content)
        if sn and _depth(sn) <= start_depth:
            end = j
            break
    return chunks[head:end]


async def build_section_context(
    session: AsyncSession,
    doc_id: int,
    heading_chunk_id: int,
    *,
    budget: int = _DEFAULT_SECTION_BUDGET,
) -> ChatContext:
    """Section context anchored at a heading chunk. Small/medium sections
    (<= budget chars) are included whole; larger sections are an explicit
    DEGRADED state — heading + budget-fit chunks + a notice (challenge R5;
    top-K relevance = 8d-2b). ``budget`` is a coarse CHAR guard, not a token
    limit (challenge R9)."""
    chunks = await _doc_chunks(session, doc_id)
    section = section_chunk_range(chunks, heading_chunk_id)
    if not section:
        raise ChunkNotFoundError(f"no section for heading chunk {heading_chunk_id} in doc {doc_id}")
    total = len(section)
    full = sum(len(_body(c)) for c in section)
    if full <= budget:
        included = section
        truncated = False
    else:
        # Degraded: always keep the heading, then add chunks until the budget.
        included = [section[0]]
        used = len(_body(section[0]))
        for c in section[1:]:
            blen = len(_body(c))
            if used + blen > budget:
                break
            included.append(c)
            used += blen
        truncated = True
    parts = [f"[섹션: {_body(section[0]) or '(제목 없음)'}] (chunk {len(included)}/{total})"]
    if truncated:
        parts.append("[안내] 이 섹션은 길어 일부만 포함되었습니다 (정밀 검색은 추후 제공).")
    parts.append("\n".join(_render(c) for c in included))
    parts.append("---")
    return ChatContext(
        text="\n\n".join(parts),
        included_chunk_ids=[c.id for c in included],
        truncated=truncated,
        total_chunks=total,
    )


def _preview(text: str | None, max_chars: int = 200) -> str:
    if not text:
        return ""
    t = text.strip().replace("\n", " ")
    return t[: max_chars - 1] + "…" if len(t) > max_chars else t


async def build_figure_context(
    session: AsyncSession, chunk_id: int, *, radius: int = 2
) -> ChatContext:
    """Figure context (Phase 8d-2b): caption (translated or original) +
    ±radius neighbour chunks. The caption+neighbour text is also the
    cross-doc query (challenge R4) — never the image chunk's empty content."""
    fig = (
        await session.execute(
            select(Chunk).where(Chunk.id == chunk_id).options(selectinload(Chunk.translation))
        )
    ).scalar_one_or_none()
    if fig is None:
        raise ChunkNotFoundError(f"chunk {chunk_id} not found")
    chunks = await _doc_chunks(session, fig.doc_id)
    idx = next((i for i, c in enumerate(chunks) if c.id == fig.id), None)
    if idx is None:  # pragma: no cover
        raise ChunkNotFoundError(f"chunk {chunk_id} not in its own document")
    tr = fig.translation
    if tr is not None and tr.status == "translated" and (tr.caption_translated or "").strip():
        caption = (tr.caption_translated or "").strip()
    else:
        caption = (fig.caption or "").strip()
    lo = max(0, idx - radius)
    hi = min(len(chunks), idx + radius + 1)
    window = [c for c in chunks[lo:hi] if c.id != fig.id]
    neigh = "\n".join(_render(c) for c in window)
    text = f"[그림] {caption or '(캡션 없음)'}\n\n주변 맥락 (±{radius}):\n{neigh}\n---"
    query_text = " ".join([caption, *[_body(c) for c in window]]).strip()
    return ChatContext(
        text=text,
        included_chunk_ids=[fig.id, *[c.id for c in window]],
        truncated=False,
        total_chunks=len(window) + 1,
        query_text=query_text,
    )


async def build_section_context_topk(
    session: AsyncSession,
    doc_id: int,
    heading_chunk_id: int,
    *,
    question_vector: np.ndarray,
    budget: int = _DEFAULT_SECTION_BUDGET,
    top_k: int = 6,
) -> ChatContext:
    """Within-section top-K (challenge R2): over-budget section → heading +
    question-relevant chunks (``search_chunks`` restricted to the section)
    instead of a blind truncation. Small section, or zero top-K hits (no
    embeddings / all below min_chars), falls back to ``build_section_context``
    (8d-2a degraded truncation — challenge R10)."""
    chunks = await _doc_chunks(session, doc_id)
    section = section_chunk_range(chunks, heading_chunk_id)
    if not section:
        raise ChunkNotFoundError(f"no section for heading chunk {heading_chunk_id} in doc {doc_id}")
    if sum(len(_body(c)) for c in section) <= budget:
        return await build_section_context(session, doc_id, heading_chunk_id, budget=budget)
    section_ids = {c.id for c in section}
    hits = await search_chunks(
        session,
        query_vector=question_vector,
        top_k=top_k,
        within_chunk_ids=section_ids,
        exclude_chunk_ids={heading_chunk_id},
    )
    if not hits:  # no relevant/embedded chunks → 8d-2a degraded fallback
        return await build_section_context(session, doc_id, heading_chunk_id, budget=budget)
    by_id = {c.id: c for c in section}
    heading = section[0]
    picked = [by_id[h.chunk_id] for h in hits if h.chunk_id in by_id]
    included = [heading, *picked]
    head_label = _body(heading) or "(제목 없음)"
    parts = [
        f"[섹션: {head_label}] (질문 관련 top-K {len(picked)}/{len(section)} chunk)",
        "\n".join(_render(c) for c in included),
        "---",
    ]
    return ChatContext(
        text="\n\n".join(parts),
        included_chunk_ids=[c.id for c in included],
        truncated=True,
        total_chunks=len(section),
        query_text=_body(heading),
    )


async def build_cross_doc_chunk_refs(
    session: AsyncSession,
    *,
    query_vector: np.ndarray,
    doc_id: int,
    exclude_chunk_ids: set[int] | None = None,
    top_k: int = 5,
    threshold: float = 0.5,
    max_chars: int = 200,
) -> list[RelatedChunkRef]:
    """Top-K vector-similar chunks from OTHER documents (challenge R3/R4).
    Best-effort: returns ``[]`` on empty corpus / no hits. dev DB has only
    doc7 so this is empty until the 8e 7-doc migration."""
    hits = await search_chunks(
        session,
        query_vector=query_vector,
        top_k=top_k,
        threshold=threshold,
        exclude_doc_ids={doc_id},
        exclude_chunk_ids=exclude_chunk_ids or set(),
    )
    if not hits:
        return []
    details = await fetch_chunk_hit_details(session, hits)
    doc_rows = (
        await session.execute(
            select(Document.id, Document.filename).where(Document.id.in_({h.doc_id for h in hits}))
        )
    ).all()
    filenames = {did: name for did, name in doc_rows}
    refs: list[RelatedChunkRef] = []
    for hit in hits:
        d = details.get(hit.chunk_id)
        if d is None:
            continue
        chunk, tr = d
        refs.append(
            RelatedChunkRef(
                chunk_id=chunk.id,
                doc_id=hit.doc_id,
                doc_filename=filenames.get(hit.doc_id, ""),
                page_idx=chunk.page_idx,
                score=hit.score,
                original_preview=_preview(chunk.content, max_chars),
                translated_preview=(
                    _preview(tr.translated_text, max_chars)
                    if tr is not None and tr.translated_text
                    else None
                ),
            )
        )
    return refs


def render_cross_doc_refs(refs: list[RelatedChunkRef]) -> str:
    """Format cross-doc refs for the chat system message."""
    lines = ["다른 문서 관련 참조 (top-K):"]
    for r in refs:
        body = r.translated_preview or r.original_preview
        lines.append(f"  [{r.doc_filename} p.{r.page_idx} score={r.score:.2f}] {body}")
    return "\n".join(lines)


__all__ = [
    "ChatContext",
    "ChunkNotFoundError",
    "RelatedChunkRef",
    "build_chunk_context",
    "build_cross_doc_chunk_refs",
    "build_figure_context",
    "build_section_context",
    "build_section_context_topk",
    "parse_section_no",
    "render_cross_doc_refs",
    "section_chunk_range",
]
