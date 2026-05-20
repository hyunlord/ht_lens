"""Block context builder — Phase 3.

Builds a markdown snippet describing a target block plus its ±radius neighbours
on the same page. Sent to the LLM as ``system=`` for ``/explain`` and
``/messages``; never persisted in the ``messages`` table.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ht_lens.db.models import Block, Page, Translation


class BlockNotFoundError(LookupError):
    """Raised when ``build_block_context`` receives an unknown block id."""


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
) -> str:
    """Return a markdown block-context for ``block_id`` with ±radius neighbours.

    Raises :class:`BlockNotFoundError` if ``block_id`` does not exist.
    Page-boundary neighbours are silently truncated (no cross-page lookup).
    ``radius=0`` omits the neighbourhood section.
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

    parts.append("---")
    return "\n\n".join(parts)


__all__ = ["BlockNotFoundError", "build_block_context"]
