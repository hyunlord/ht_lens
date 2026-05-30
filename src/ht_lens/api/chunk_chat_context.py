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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Chunk

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


__all__ = [
    "ChatContext",
    "ChunkNotFoundError",
    "build_chunk_context",
    "build_section_context",
    "parse_section_no",
    "section_chunk_range",
]
