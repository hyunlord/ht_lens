"""Pydantic read/create schemas for the REST API — Phase 3.

These are intentionally separate from ORM models. ``BlockRead.bbox`` exposes
the JSON-encoded ``bbox_json`` as a list of floats; routers do the conversion.

Finite-domain attributes (``BlockRead.type``, ``MessageRead.role``) are typed
as :class:`Literal` so Phase 4/5 clients can rely on the contract. ``status``
fields remain ``str`` because the project still introduces new values across
phases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BlockType = Literal["text", "image", "header", "table"]
MessageRole = Literal["user", "assistant", "system"]


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    src_lang: str
    tgt_lang: str
    status: str
    src_pdf_sha256: str | None = None
    num_pages: int
    created_at: datetime
    # Phase 6d: auto-generated abstract (Korean, 300~500 words). ``None``
    # while the summarize stage is still pending or skipped (image-only doc).
    summary: str | None = None
    summarized_at: datetime | None = None


class JobRead(BaseModel):
    """Background job state — Phase 6d."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    document_id: int | None = None
    upload_filename: str | None = None
    upload_sha256: str | None = None
    progress_pct: int
    progress_message: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class UploadResponse(BaseModel):
    """``POST /uploads`` response — Phase 6d.

    ``dedup=True`` means the file was already ingested; ``document_id``
    points at the existing document and no job was created. Otherwise a
    new job is spawned and ``job_id`` is non-null.
    """

    job_id: int | None
    document_id: int | None
    dedup: bool


class BlockRead(BaseModel):
    id: int
    block_local_id: str
    type: BlockType
    bbox: list[float]
    order: int
    original_text: str
    translated_text: str | None
    has_thread: bool


class PageRender(BaseModel):
    dpi: int
    pixel_w: int
    pixel_h: int
    scale: float


class PageSummary(BaseModel):
    """Lightweight per-page metadata for the natural-scroll viewer — Phase 6b.

    Excludes blocks intentionally — placeholder rows can be sized from the
    render dimensions alone; blocks load on demand when a page enters the
    viewport.
    """

    page_num: int
    width: float
    height: float
    rotation: int
    render: PageRender


class PageRead(BaseModel):
    page_num: int
    width: float
    height: float
    rotation: int
    render: PageRender
    blocks: list[BlockRead]


class RelatedBlock(BaseModel):
    """Phase 7a — one cross-doc vector-search hit surfaced into chat.

    Mirrors :class:`ht_lens.api.chat_context.RelatedBlockRef`. Used by
    ``/blocks/{id}/related`` and by ``MessageRead.related_blocks`` so
    the viewer can render "다른 책의 관련 부분" links (ROADMAP DoD ④).
    """

    block_id: int
    doc_id: int
    doc_filename: str
    page_num: int
    block_local_id: str
    score: float
    original_preview: str
    translated_preview: str | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    model: str | None = None
    created_at: datetime
    # Phase 7a: cross-doc references the LLM saw in its system context.
    # Empty when RAG is disabled, embedding client unavailable, or no
    # hit cleared the threshold. Not persisted (computed per response).
    related_blocks: list[RelatedBlock] = []


class ThreadSummary(BaseModel):
    id: int
    block_id: int
    title: str
    page_num: int
    message_count: int
    created_at: datetime


class ThreadDetail(BaseModel):
    id: int
    block_id: int
    title: str
    block: BlockRead
    page_num: int
    messages: list[MessageRead]
    created_at: datetime


class ThreadCreate(BaseModel):
    block_id: int
    title: str | None = None


class MessageCreate(BaseModel):
    """User message body. Rejects empty / whitespace-only content."""

    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def _non_whitespace(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("content must not be empty or whitespace-only")
        return value


# Phase 6a additions


class SearchHit(BaseModel):
    """One result row from ``GET /search``.

    ``preview`` already contains a single inline ``<mark>...</mark>`` around
    the first occurrence of the matched substring; the client renders it via
    DOMPurify with ``<mark>`` whitelisted.
    """

    doc_id: int
    doc_filename: str
    page_num: int
    block_id: int
    block_local_id: str
    type: BlockType
    matched_field: Literal["original", "translated"]
    preview: str


class TranslationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_id: int
    translated_text: str
    model: str
    status: str


class RetranslateResponse(BaseModel):
    block_id: int
    translation: TranslationRead


# --- Phase 8d-2a: chunk chat (ht_lens 2.0) ---

ChunkAnchorType = Literal["chunk", "section"]


class ChunkThreadCreate(BaseModel):
    """Create a 2.0 chat thread. ``anchor_type='chunk'`` → paragraph Q&A;
    ``anchor_type='section'`` → ``chunk_id`` is the section's HEADING chunk
    (challenge R1)."""

    doc_id: int
    anchor_type: ChunkAnchorType
    chunk_id: int
    title: str | None = None


class ChunkMessageCreate(BaseModel):
    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def _non_whitespace(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("content must not be empty or whitespace-only")
        return value


class ChunkRelatedRef(BaseModel):
    """Phase 8d-2b — one cross-doc chunk surfaced into chat (mirrors
    RelatedBlock; challenge R3). Returned in the API response, not only the
    system prompt, so UI + tests can verify it."""

    chunk_id: int
    doc_id: int
    doc_filename: str
    page_idx: int
    score: float
    original_preview: str
    translated_preview: str | None = None


class ChunkMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    model: str | None = None
    created_at: datetime
    # Phase 8d-2b: cross-doc chunk refs the LLM saw (empty when RAG disabled,
    # embedding client unavailable, or no hit — dev DB has only doc7).
    related_chunks: list[ChunkRelatedRef] = []


class ChunkThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_id: int
    anchor_type: ChunkAnchorType
    chunk_id: int
    title: str
    created_at: datetime


class ChunkThreadSummary(BaseModel):
    id: int
    doc_id: int
    anchor_type: ChunkAnchorType
    chunk_id: int
    title: str
    message_count: int
    created_at: datetime


class ChunkPinCreate(BaseModel):
    doc_id: int
    chunk_id: int


class ChunkPinRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_id: int
    chunk_id: int
    created_at: datetime


__all__ = [
    "BlockRead",
    "BlockType",
    "ChunkAnchorType",
    "ChunkMessageCreate",
    "ChunkMessageRead",
    "ChunkPinCreate",
    "ChunkPinRead",
    "ChunkRelatedRef",
    "ChunkThreadCreate",
    "ChunkThreadRead",
    "ChunkThreadSummary",
    "DocumentRead",
    "JobRead",
    "MessageCreate",
    "MessageRead",
    "MessageRole",
    "PageRead",
    "PageRender",
    "PageSummary",
    "RetranslateResponse",
    "SearchHit",
    "ThreadCreate",
    "ThreadDetail",
    "ThreadSummary",
    "TranslationRead",
    "UploadResponse",
]
