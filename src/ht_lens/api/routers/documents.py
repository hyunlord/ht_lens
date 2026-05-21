"""``/documents`` router — Phase 3."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.api.deps import get_llm_client, get_session
from ht_lens.api.export_markdown import build_questions_markdown
from ht_lens.api.schemas import DocumentRead
from ht_lens.db.models import Document, Page
from ht_lens.llm.client import LLMClient
from ht_lens.summarize.pipeline import SummarizeEmptyError, summarize_document

router = APIRouter(prefix="/documents", tags=["documents"])


async def _document_with_page_count(
    session: AsyncSession, doc_id: int
) -> tuple[Document, int] | None:
    doc = (
        await session.execute(select(Document).where(Document.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        return None
    count_row = await session.execute(
        select(func.count()).select_from(Page).where(Page.doc_id == doc_id)
    )
    return doc, int(count_row.scalar_one())


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentRead]:
    stmt = select(Document).order_by(Document.id.asc())
    if status_filter is not None:
        stmt = stmt.where(Document.status == status_filter)
    stmt = stmt.offset(offset).limit(limit)
    docs = (await session.execute(stmt)).scalars().all()
    if not docs:
        return []
    doc_ids = [d.id for d in docs]
    count_rows = await session.execute(
        select(Page.doc_id, func.count()).where(Page.doc_id.in_(doc_ids)).group_by(Page.doc_id)
    )
    counts: dict[int, int] = {doc_id: int(c) for doc_id, c in count_rows.all()}
    return [
        DocumentRead(
            id=d.id,
            filename=d.filename,
            src_lang=d.src_lang,
            tgt_lang=d.tgt_lang,
            status=d.status,
            src_pdf_sha256=d.src_pdf_sha256,
            num_pages=counts.get(d.id, 0),
            created_at=d.created_at,
            summary=d.summary,
            summarized_at=d.summarized_at,
        )
        for d in docs
    ]


@router.get("/{doc_id}", response_model=DocumentRead)
async def get_document(
    doc_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentRead:
    pair = await _document_with_page_count(session, doc_id)
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    doc, num_pages = pair
    return DocumentRead(
        id=doc.id,
        filename=doc.filename,
        src_lang=doc.src_lang,
        tgt_lang=doc.tgt_lang,
        status=doc.status,
        src_pdf_sha256=doc.src_pdf_sha256,
        num_pages=num_pages,
        created_at=doc.created_at,
        summary=doc.summary,
        summarized_at=doc.summarized_at,
    )


@router.get("/{doc_id}/export.md")
async def export_questions_markdown(
    doc_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Stream a UTF-8 markdown export of every thread on this document.

    ASCII-safe filename so we don't hit RFC 5987 encoding edge cases on
    older browsers. Returns 404 if the document does not exist.
    """
    md = await build_questions_markdown(session, doc_id)
    if md is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    filename = f"ht_lens-{doc_id}-questions.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{doc_id}/summarize",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def summarize_route(
    doc_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> DocumentRead:
    """Phase 6d: manually (re-)generate the auto-summary for a document.

    Used by the viewer banner's "재생성" button when the original
    upload-pipeline summarize stage was skipped or failed. Empty-source
    documents (image-only PDF, not-yet-translated) raise 422 with a
    clear Korean message.
    """
    pair = await _document_with_page_count(session, doc_id)
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    doc, num_pages = pair
    try:
        summary = await summarize_document(doc_id, session, llm)
    except SummarizeEmptyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    doc.summary = summary
    doc.summarized_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(doc)
    return DocumentRead(
        id=doc.id,
        filename=doc.filename,
        src_lang=doc.src_lang,
        tgt_lang=doc.tgt_lang,
        status=doc.status,
        src_pdf_sha256=doc.src_pdf_sha256,
        num_pages=num_pages,
        created_at=doc.created_at,
        summary=doc.summary,
        summarized_at=doc.summarized_at,
    )


__all__ = ["router"]
