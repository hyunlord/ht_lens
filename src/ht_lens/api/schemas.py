"""Pydantic read/create schemas for the REST API — Phase 3.

These are intentionally separate from ORM models. ``BlockRead.bbox`` exposes
the JSON-encoded ``bbox_json`` as a list of floats; routers do the conversion.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class BlockRead(BaseModel):
    id: int
    block_local_id: str
    type: str
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


class PageRead(BaseModel):
    page_num: int
    width: float
    height: float
    rotation: int
    render: PageRender
    blocks: list[BlockRead]


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    model: str | None = None
    created_at: datetime


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
    content: str = Field(..., min_length=1)


__all__ = [
    "BlockRead",
    "DocumentRead",
    "MessageCreate",
    "MessageRead",
    "PageRead",
    "PageRender",
    "ThreadCreate",
    "ThreadDetail",
    "ThreadSummary",
]
