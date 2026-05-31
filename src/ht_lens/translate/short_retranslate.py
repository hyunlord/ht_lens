"""Phase 8d-2c — neighbour-context re-translation of short/low-context chunks.

A very short fragment translated in isolation can be wrong: "where" (after an
equation) becomes the locative "어디에" instead of the connective "여기서".
This re-translates such fragments WITH their neighbours as context.

Conservative selection (Stage 0 + challenge): only ``< max_chars`` text chunks,
excluding reference numbers (regex, not a digit-ratio that would drop "K=10")
and math; copyright boilerplate is excluded by the length bound itself (no
repeat-count heuristic — that would wrongly drop a legitimately repeated
"where", challenge R4). Neighbours are ALL types, labelled — the equation a
"where" refers to must be in context (challenge R7), not text-only.

Safety: the re-translation BYPASSES the content-only cache and stores
``cache_key=NULL`` so a context-specific phrase never poisons a future
identical-source chunk (challenge R1). A lost math placeholder or empty output
PRESERVES the existing translation (8b no-write, challenge R3).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Chunk, ChunkTranslation, Document
from ht_lens.llm.client import TranslateLLMClient
from ht_lens.translate import math_protect

_DEFAULT_MAX_CHARS = 25
# Bare equation/figure/table/citation numbers: "(28.116)", "Eq. 3", "Fig. 2",
# "Table 1", "28.4.2", "(A.1)" (appendix), "[12]". The optional single-letter
# appendix prefix needs a trailing dot, so "K=10"/"p=0.5" (no dot after the
# letter, plus an "=") never match — NOT a digit-ratio (debate §3, challenge R5).
_REF_NUMBER_RE = re.compile(
    r"^\s*(?:eq\.?|fig\.?|figure|table)?\s*\(?(?:[A-Z]\.)?\d+(?:\.\d+)*\)?[.:]?\s*$", re.I
)
_BRACKET_CITE_RE = re.compile(r"^\s*\[\d+\]\s*$")
_TYPE_LABEL = {
    "heading": "섹션",
    "text": "본문",
    "equation": "수식",
    "image": "그림",
    "table": "표",
}


def is_math_dense(text: str) -> bool:
    """``$``-math or LaTeX ``\\(..\\)`` / ``\\[..\\]`` present (selector safety;
    challenge R6 — math_protect itself only handles ``$`` and is 8e's job)."""
    return math_protect.has_math(text) or "\\(" in text or "\\[" in text


def is_reference_number(text: str) -> bool:
    """A bare equation/figure/table/citation number — never a mistranslation
    candidate (challenge R5)."""
    t = text.strip()
    return bool(_REF_NUMBER_RE.match(t) or _BRACKET_CITE_RE.match(t))


@dataclass
class ShortRetranslateStats:
    candidates: int = 0
    retranslated: int = 0
    failed: int = 0
    # (chunk_id, before, after) — populated only for dry_run preview.
    previews: list[tuple[int, str, str]] = field(default_factory=list)


def _label(c: Chunk) -> str:
    return _TYPE_LABEL.get(c.type, c.type)


def select_short_retranslate(
    chunks: list[Chunk], translations: dict[int, ChunkTranslation], *, max_chars: int
) -> list[Chunk]:
    """Translated text chunks shorter than ``max_chars``, excluding reference
    numbers and math (challenge R4/R5/R6)."""
    out: list[Chunk] = []
    for c in chunks:
        if c.type != "text":
            continue
        body = (c.content or "").strip()
        if not body or len(body) >= max_chars:
            continue
        if is_reference_number(body) or is_math_dense(body):
            continue
        tr = translations.get(c.id)
        if tr is None or tr.status != "translated":
            continue  # only re-translate an existing successful translation
        out.append(c)
    return out


def _neighbor_context(chunks: list[Chunk], idx: int, *, radius: int = 1) -> str:
    """Labelled all-type neighbours (challenge R7 — includes the equation/
    heading a short fragment refers to; NOT text-only)."""
    lo = max(0, idx - radius)
    hi = min(len(chunks), idx + radius + 1)
    return "\n".join(
        f"[{_label(chunks[j])}] {(chunks[j].content or '').strip()}"
        for j in range(lo, hi)
        if j != idx
    )


async def _translate_with_context(
    llm: TranslateLLMClient, text: str, src: str, tgt: str, context: str
) -> str:
    """protect → translate(with neighbour context) → restore. Raises if the
    LLM dropped a math placeholder (caller preserves the existing row)."""
    prefix = "MATH"
    if math_protect.source_has_placeholder_collision(text):
        prefix = "MATH" + hashlib.sha1(text.encode()).hexdigest()[:10].upper()
    protected, store = math_protect.protect_math(text, token_prefix=prefix)
    out = await llm.translate(protected, src, tgt, context=context)
    restored, missing = math_protect.restore_math(out, store, token_prefix=prefix)
    if missing:
        raise ValueError(f"{len(missing)} math placeholder(s) lost by LLM")
    return restored


async def retranslate_short(
    session: AsyncSession,
    doc: Document,
    llm: TranslateLLMClient,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    chunk_ids: set[int] | None = None,
    dry_run: bool = False,
) -> ShortRetranslateStats:
    """Re-translate short low-context chunks (or explicit ``chunk_ids``) with
    neighbour context. ``dry_run`` collects before/after without writing. Each
    written row uses ``cache_key=NULL`` (challenge R1)."""
    chunks = list(
        (
            await session.execute(
                select(Chunk).where(Chunk.doc_id == doc.id).order_by(Chunk.order_idx)
            )
        ).scalars()
    )
    tr_rows = (
        await session.execute(
            select(ChunkTranslation).where(ChunkTranslation.chunk_id.in_([c.id for c in chunks]))
        )
    ).scalars()
    translations = {t.chunk_id: t for t in tr_rows}
    if chunk_ids is not None:
        # Explicit repair path: every requested id must exist in this doc.
        # Silently dropping unknown / wrong-document ids (candidates=0, exit 0)
        # would make a typo look like success (verify-cross 8d-2c R1 defect B).
        missing = chunk_ids - {c.id for c in chunks}
        if missing:
            raise ValueError(f"chunk_id(s) not found in doc {doc.id}: {sorted(missing)}")
        targets = [c for c in chunks if c.id in chunk_ids]
    else:
        targets = select_short_retranslate(chunks, translations, max_chars=max_chars)
    stats = ShortRetranslateStats(candidates=len(targets))
    index = {c.id: i for i, c in enumerate(chunks)}
    model = str(getattr(llm, "model_name", "unknown"))
    for c in targets:
        ctx = _neighbor_context(chunks, index[c.id])
        existing = translations.get(c.id)
        before = existing.translated_text if existing is not None else ""
        try:
            after = await _translate_with_context(llm, c.content, doc.src_lang, doc.tgt_lang, ctx)
        except Exception:
            # Any failure (LLM error or lost math placeholder) preserves the
            # existing row — never degrade a valid translation (8b, challenge R3).
            stats.failed += 1
            continue
        if not after.strip():
            stats.failed += 1
            continue
        if dry_run:
            stats.previews.append((c.id, before, after))
            continue
        now = datetime.now(UTC)
        if existing is not None:
            existing.translated_text = after
            existing.cache_key = None  # context-specific → don't poison the content cache (R1)
            existing.model = model
            existing.status = "translated"
            existing.updated_at = now
        else:
            session.add(
                ChunkTranslation(
                    chunk_id=c.id,
                    translated_text=after,
                    caption_translated=None,
                    model=model,
                    cache_key=None,
                    status="translated",
                    updated_at=now,
                )
            )
        stats.retranslated += 1
    if not dry_run:
        await session.commit()
    return stats


__all__ = [
    "ShortRetranslateStats",
    "is_math_dense",
    "is_reference_number",
    "retranslate_short",
    "select_short_retranslate",
]
