"""Document summarization — Phase 6d.

Single-shot LLM summarisation of a translated document. The pipeline
collects the first ``MAX_SUMMARY_CHARS`` of translated text in
page→block order and asks the LLM for a 300~500 word Korean abstract.

Hierarchical (page-by-page → roll-up) summarisation is deferred to
Phase 6e — single-shot keeps the cost predictable (~10 s) and is
sufficient for the v0.7 milestone.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Block, Document, Page, Translation
from ht_lens.llm.client import ChatLLMClient

# Empirical cap: ~8 KB of Korean text fits comfortably under the qwen3.6
# 32k context window with headroom for the prompt and the response.
MAX_SUMMARY_CHARS = 8_000


class SummarizeEmptyError(ValueError):
    """Raised when the document has no translated text to summarise.

    The upload pipeline catches this and finishes the job with
    ``status=done`` + ``error_message`` explaining the skip; the
    ``POST /documents/{id}/summarize`` endpoint maps it to HTTP 422.
    """


def build_summary_prompt(body: str) -> str:
    """The Korean prompt used by :func:`summarize_document`.

    Exposed for test grep + future tuning. Keep the structure stable
    so downstream tests can pin specific phrases.
    """
    return (
        "다음은 한국어로 번역된 문서의 일부입니다.\n"
        "이 문서의 핵심을 한국어로 300~500 단어 분량으로 요약해주세요.\n"
        "다음 항목을 포함하세요:\n"
        "- 문서 주제와 범위\n"
        "- 핵심 주장 또는 발견\n"
        "- 주요 결론\n"
        "\n"
        "문서:\n" + body
    )


async def _fetch_translated_text(
    doc_id: int, session: AsyncSession, *, max_chars: int = MAX_SUMMARY_CHARS
) -> str:
    """Concatenate the document's translated block text in reading order,
    capped at ``max_chars``. Header/text blocks only — image blocks are
    skipped (they have no translation)."""
    stmt = (
        select(Translation.translated_text)
        .select_from(Block)
        .join(Page, Page.id == Block.page_id)
        .outerjoin(Translation, Translation.block_id == Block.id)
        .where(Page.doc_id == doc_id)
        .where(Block.type.in_(["text", "header"]))
        .order_by(Page.page_num.asc(), Block.order_idx.asc())
    )
    rows = (await session.execute(stmt)).all()

    chunks: list[str] = []
    total = 0
    for (translated,) in rows:
        text = translated or ""
        if not text:
            continue
        chunks.append(text)
        total += len(text) + 2  # +2 for the join separator
        if total >= max_chars:
            break
    return "\n\n".join(chunks)[:max_chars]


async def summarize_document(doc_id: int, session: AsyncSession, llm: ChatLLMClient) -> str:
    """Generate a Korean abstract for ``doc_id``. The caller commits
    ``Document.summary`` / ``summarized_at`` — this function is pure
    (no DB writes) so it can be reused by the upload pipeline and the
    explicit ``POST /summarize`` endpoint.

    Raises :class:`SummarizeEmptyError` when the document has no
    translated text (image-only PDF or pre-translate state).
    """
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"document {doc_id} not found")
    body = await _fetch_translated_text(doc_id, session)
    if not body.strip():
        raise SummarizeEmptyError(
            "번역된 텍스트가 없어 자동 요약을 생략했습니다 "
            "(이미지 전용 PDF이거나 번역 단계가 미완료)"
        )
    prompt = build_summary_prompt(body)
    response = await llm.chat([{"role": "user", "content": prompt}])
    return response.strip()
