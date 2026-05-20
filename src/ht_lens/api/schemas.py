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
    role: MessageRole
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
    """User message body. Rejects empty / whitespace-only content."""

    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def _non_whitespace(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("content must not be empty or whitespace-only")
        return value


__all__ = [
    "BlockRead",
    "BlockType",
    "DocumentRead",
    "MessageCreate",
    "MessageRead",
    "MessageRole",
    "PageRead",
    "PageRender",
    "ThreadCreate",
    "ThreadDetail",
    "ThreadSummary",
]
