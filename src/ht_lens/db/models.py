"""ORM models — Phase 2a schema (7 tables).

PK strategy: every table uses surrogate ``int`` primary keys. Phase 1 block
identifiers (``p1_b001``) are preserved in :attr:`Block.block_local_id` with
**no** global-uniqueness assumption — collisions across documents are expected.

``bbox_json`` stores ``[x0, y0, x1, y1]`` as a JSON string; :attr:`Block.bbox`
exposes it as a tuple for callers.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ht_lens.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str]
    src_lang: Mapped[str]
    tgt_lang: Mapped[str]
    status: Mapped[str]
    created_at: Mapped[datetime]
    src_pdf_sha256: Mapped[str | None]
    # Phase 6d: auto-generated abstract (300~500 단어 한국어), null until the
    # summarize stage of process_upload_job finishes.
    summary: Mapped[str | None] = mapped_column(default=None)
    summarized_at: Mapped[datetime | None] = mapped_column(default=None)
    # Phase 8a (2.0): which extractor produced this document. 1.x rows keep
    # the default 'pymupdf'; MinerU-ingested 2.0 docs are 'mineru'. Lets the
    # same DB host both pipelines (parallel-DB decision) without ambiguity.
    extractor: Mapped[str] = mapped_column(default="pymupdf")
    # Path to the MinerU markdown export kept for audit/re-ingest (2.0 only).
    markdown_path: Mapped[str | None] = mapped_column(default=None)

    pages: Mapped[list[Page]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Page.page_num",
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Chunk.order_idx",
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    page_num: Mapped[int]
    width: Mapped[float]
    height: Mapped[float]
    bg_image_path: Mapped[str]
    rotation: Mapped[int] = mapped_column(default=0)
    render_dpi: Mapped[int] = mapped_column(default=200)
    pixel_width: Mapped[int]
    pixel_height: Mapped[int]

    document: Mapped[Document] = relationship(back_populates="pages")
    blocks: Mapped[list[Block]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="Block.order_idx",
    )


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    block_local_id: Mapped[str]
    type: Mapped[str]
    bbox_json: Mapped[str]
    order_idx: Mapped[int]
    original_text: Mapped[str]

    page: Mapped[Page] = relationship(back_populates="blocks")
    translation: Mapped[Translation | None] = relationship(
        back_populates="block",
        cascade="all, delete-orphan",
        uselist=False,
    )
    threads: Mapped[list[Thread]] = relationship(
        back_populates="block",
        cascade="all, delete-orphan",
    )

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Decode ``bbox_json`` into ``(x0, y0, x1, y1)``."""
        raw = json.loads(self.bbox_json)
        x0, y0, x1, y1 = raw
        return (float(x0), float(y0), float(x1), float(y1))


class Chunk(Base):
    """ht_lens 2.0 (Phase 8a) — one MinerU ``content_list`` item.

    Item-level granularity: a chunk is the unit of reflow display,
    translation (8b), embedding (8b), and chat anchoring (8d). It carries
    enough structure to render a flowed reading view without the PDF
    layout: ``type`` (text/heading/equation/image/table/unknown),
    ``text_level`` (heading depth), and ``content`` (body text, LaTeX, or
    table markup).

    ``page_idx`` is MinerU's 0-based page index, stored as a plain int with
    **no FK to ``pages``** — Phase 8a does not create ``pages`` rows
    (their render columns are NOT NULL and the side-by-side PDF render is a
    Phase 8c concern). ``bbox_json`` keeps MinerU's raw coordinates
    verbatim (provenance); px↔pt reconciliation is deferred to 8c.
    """

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    page_idx: Mapped[int]
    order_idx: Mapped[int]
    type: Mapped[str]
    text_level: Mapped[int | None] = mapped_column(default=None)
    bbox_json: Mapped[str]
    content: Mapped[str]
    text_format: Mapped[str | None] = mapped_column(default=None)
    img_path: Mapped[str | None] = mapped_column(default=None)
    caption: Mapped[str | None] = mapped_column(default=None)

    document: Mapped[Document] = relationship(back_populates="chunks")
    translation: Mapped[ChunkTranslation | None] = relationship(
        back_populates="chunk",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def bbox(self) -> list[float]:
        """Decode ``bbox_json`` into a list (``[]`` when provenance was absent)."""
        raw = json.loads(self.bbox_json)
        return [float(v) for v in raw]


class ChunkTranslation(Base):
    """ht_lens 2.0 (Phase 8b) — translation of one chunk.

    ``translated_text`` holds: KO translation for text/heading/table,
    the LaTeX verbatim for equation (``model='passthrough'``), or ``""``
    for image chunks with no translatable body. ``caption_translated``
    is the KO caption for any caption-bearing chunk (image/chart/table).
    ``cache_key`` is ``cache_key(content, src, tgt, model)`` so identical
    source content dedups across the run (Phase 7a-2 5.66x).
    """

    __tablename__ = "chunk_translations"

    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
    )
    translated_text: Mapped[str]
    caption_translated: Mapped[str | None] = mapped_column(default=None)
    model: Mapped[str]
    cache_key: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str]
    updated_at: Mapped[datetime]

    chunk: Mapped[Chunk] = relationship(back_populates="translation")


class ChunkEmbedding(Base):
    """ht_lens 2.0 (Phase 8b) — one vector per translated text/heading chunk.

    Mirrors ``BlockEmbedding`` exactly (bge-m3, raw float32 bytes,
    idempotent ``source_hash``); the chunk path is added alongside the 1.x
    block path rather than renaming it, so 1.x RAG stays intact.
    """

    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str]
    dim: Mapped[int]
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    source_hash: Mapped[str]
    updated_at: Mapped[datetime]


class ChunkThread(Base):
    """ht_lens 2.0 (Phase 8d-2a) — a chat thread anchored to a chunk.

    ``anchor_type='chunk'`` → paragraph Q&A (that chunk + neighbours).
    ``anchor_type='section'`` → anchors to the section's HEADING chunk; the
    server derives the section range from it (challenge R1: a concrete
    ``chunk_id`` avoids ``sec_no`` ambiguity for duplicate/unnumbered
    headings). New table; the 1.x ``threads`` table is untouched.
    """

    __tablename__ = "chunk_threads"
    __table_args__ = (
        CheckConstraint("anchor_type IN ('chunk', 'section')", name="ck_chunk_threads_anchor_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    anchor_type: Mapped[str]
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    title: Mapped[str]
    created_at: Mapped[datetime]

    messages: Mapped[list[ChunkMessage]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChunkMessage.id",
    )


class ChunkMessage(Base):
    """ht_lens 2.0 (Phase 8d-2a) — one message in a chunk chat thread."""

    __tablename__ = "chunk_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("chunk_threads.id", ondelete="CASCADE"))
    role: Mapped[str]
    content: Mapped[str]
    model: Mapped[str | None]
    created_at: Mapped[datetime]

    thread: Mapped[ChunkThread] = relationship(back_populates="messages")


class ChunkPin(Base):
    """ht_lens 2.0 (Phase 8d-2a) — a bookmarked chunk, separate from threads
    (challenge R3: pins are not overloaded conversation threads)."""

    __tablename__ = "chunk_pins"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    created_at: Mapped[datetime]


class Translation(Base):
    __tablename__ = "translations"

    block_id: Mapped[int] = mapped_column(
        ForeignKey("blocks.id"),
        primary_key=True,
    )
    translated_text: Mapped[str]
    model: Mapped[str]
    cache_key: Mapped[str | None]
    status: Mapped[str]
    updated_at: Mapped[datetime]

    block: Mapped[Block] = relationship(back_populates="translation")


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id"))
    title: Mapped[str]
    created_at: Mapped[datetime]

    block: Mapped[Block] = relationship(back_populates="threads")
    messages: Mapped[list[Message]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"))
    role: Mapped[str]
    content: Mapped[str]
    model: Mapped[str | None]
    created_at: Mapped[datetime]

    thread: Mapped[Thread] = relationship(back_populates="messages")


class Job(Base):
    """Background-job tracking — Phase 6d.

    Drives the ``POST /uploads`` → extract → ingest → translate → summarize
    pipeline. One row per upload; the linear status machine is
    ``pending → extracting → ingesting → translating → summarizing → done``
    (``failed`` from anywhere). ``document_id`` is set once ingest succeeds.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str]
    status: Mapped[str]
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), default=None
    )
    upload_path: Mapped[str | None] = mapped_column(default=None)
    upload_filename: Mapped[str | None] = mapped_column(default=None)
    upload_sha256: Mapped[str | None] = mapped_column(default=None)
    progress_pct: Mapped[int] = mapped_column(default=0)
    progress_message: Mapped[str | None] = mapped_column(default=None)
    error_message: Mapped[str | None] = mapped_column(default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime]


class BlockEmbedding(Base):
    """Phase 7a — one vector per translated block (bge-m3, 1024d).

    See ``src/ht_lens/db/migrations/versions/0004_block_embeddings.py``
    for column rationale. ``vector`` is raw ``numpy float32`` bytes
    (``len == dim * 4``); ``source_hash`` is the SHA-256 of the source
    text at embed time and drives idempotent backfill.
    """

    __tablename__ = "block_embeddings"

    block_id: Mapped[int] = mapped_column(
        ForeignKey("blocks.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str]
    dim: Mapped[int]
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    source_hash: Mapped[str]
    updated_at: Mapped[datetime]


__all__ = [
    "Base",
    "Block",
    "BlockEmbedding",
    "Chunk",
    "ChunkEmbedding",
    "ChunkTranslation",
    "Document",
    "Job",
    "Message",
    "Page",
    "Thread",
    "Translation",
]
