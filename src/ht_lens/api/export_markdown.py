"""Build a markdown document summarising every thread (with its messages) for
a single document. Used by ``GET /documents/{id}/export.md``.

Every user/assistant content line is prefixed with ``> `` so headings, code
fences, and raw HTML inside a message cannot break the outer section
structure (Phase 6a debate §2 / §5).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Block, Document, Page, Thread


def _quote(text: str) -> str:
    """Prefix every line (including empty ones) with ``> `` so the content is
    safely contained inside a markdown blockquote even if it has its own
    headings, lists, or fences."""
    if not text:
        return ">"
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _truncate(text: str, limit: int = 300) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def build_questions_markdown(session: AsyncSession, doc_id: int) -> str | None:
    """Return the markdown export for ``doc_id``. ``None`` if the document
    does not exist."""
    doc = await session.get(Document, doc_id)
    if doc is None:
        return None

    page_count = (await session.execute(select(Page.id).where(Page.doc_id == doc_id))).all()

    rows = (
        (
            await session.execute(
                select(Thread)
                .options(
                    selectinload(Thread.messages),
                    selectinload(Thread.block).selectinload(Block.page),
                    selectinload(Thread.block).selectinload(Block.translation),
                )
                .join(Block, Block.id == Thread.block_id)
                .join(Page, Page.id == Block.page_id)
                .where(Page.doc_id == doc_id)
                .order_by(Page.page_num.asc(), Block.order_idx.asc(), Thread.id.asc())
            )
        )
        .scalars()
        .all()
    )

    non_empty = [t for t in rows if len(t.messages) > 0]

    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    lines: list[str] = [
        f"# {doc.filename} — 질문 모음",
        "",
        f"- 문서: {doc.filename}",
        f"- 페이지 수: {len(page_count)}",
        f"- 질문 수: {len(non_empty)}",
        f"- 생성: {now}",
        "",
        "---",
        "",
    ]
    for thread in non_empty:
        block = thread.block
        page = block.page
        translation = block.translation
        lines.append(f"## p.{page.page_num} — {block.block_local_id}")
        lines.append("")
        # R1 fix: multi-line original/translated must stay inside the
        # blockquote. ``_quote`` prefixes every line; the leading "원문:" /
        # "번역:" label sits on its own line so the body keeps indentation.
        lines.append("> 원문:")
        lines.append(_quote(_truncate(block.original_text)))
        if translation is not None and translation.translated_text:
            lines.append("> 번역:")
            lines.append(_quote(_truncate(translation.translated_text)))
        lines.append("")
        lines.append(f"### {thread.title}")
        lines.append("")
        for msg in sorted(thread.messages, key=lambda m: m.id):
            stamp = msg.created_at.isoformat(timespec="seconds")
            if msg.role == "assistant":
                model = msg.model or "assistant"
                lines.append(f"**AI** ({model}, {stamp}):")
            else:
                lines.append(f"**나** ({stamp}):")
            lines.append("")
            lines.append(_quote(msg.content or ""))
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["build_questions_markdown"]
