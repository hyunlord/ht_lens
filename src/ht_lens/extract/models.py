"""Public JSON schemas for extracted documents.

Pydantic models are used only for ``model_dump_json`` serialization stability.
No domain validation logic lives here — see Phase 2+ for that.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BlockType = Literal["text", "image", "header"]


class Block(BaseModel):
    id: str
    type: BlockType
    bbox: tuple[float, float, float, float]
    order: int
    text: str


class RenderInfo(BaseModel):
    dpi: int
    pixel_width: int
    pixel_height: int
    scale: float


class PageDoc(BaseModel):
    page_num: int
    width: float
    height: float
    rotation: int
    render: RenderInfo
    unit: Literal["pt"] = "pt"
    blocks: list[Block] = Field(default_factory=list)


class DocMeta(BaseModel):
    filename: str
    num_pages: int
    lang_guess: Literal["en", "ko", "mixed", "unknown"]
    src_pdf_sha256: str
    extracted_at: str
    extractor_version: str
