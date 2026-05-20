"""Ingest Phase 1 extract output into the Phase 2a SQLite schema."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Block, Document, Page
from ht_lens.db.session import ALEMBIC_HEAD, current_schema_version
from ht_lens.errors import (
    DocumentAlreadyIngested,
    IngestError,
    SchemaVersionMismatch,
)
from ht_lens.extract.models import DocMeta, PageDoc

PAGE_FILENAME_RE = re.compile(r"^page_(\d{4})\.json$")


@dataclass(frozen=True)
class IngestStats:
    """Outcome of one ``ingest_extract_dir`` invocation."""

    document_id: int
    pages: int
    blocks: int


async def ingest_extract_dir(
    extract_dir: Path,
    session: AsyncSession,
    *,
    src: str | None,
    tgt: str = "ko",
    overwrite: bool = False,
) -> IngestStats:
    """Atomically ingest ``extract_dir`` (Phase 1 layout) into ``session``.

    The caller owns transaction commit/rollback. On failure the session is
    rolled back (no caller cleanup needed for partial rows). If ``overwrite`` is
    true, an existing document with the same ``filename`` is cascade-deleted
    inside the same transaction so rollback restores it.
    """
    if not extract_dir.exists() or not extract_dir.is_dir():
        raise IngestError(f"extract directory not found: {extract_dir}")

    await _require_schema_head(session)

    doc_meta = _load_doc_meta(extract_dir)
    src_lang = _resolve_src_lang(doc_meta, src)

    page_files = _discover_page_files(extract_dir, doc_meta)
    page_docs = _load_page_docs(page_files)

    try:
        existing = (
            await session.execute(select(Document).where(Document.filename == doc_meta.filename))
        ).scalar_one_or_none()

        if existing is not None and not overwrite:
            raise DocumentAlreadyIngested(
                f"document already ingested: {doc_meta.filename!r}. Use --overwrite to replace."
            )
        if existing is not None:
            # Bulk DML bypasses ORM cascade, so delete bottom-up to satisfy FK constraints.
            # Same transaction — downstream failure rolls back all deletes.
            await session.execute(
                delete(Block).where(
                    Block.page_id.in_(select(Page.id).where(Page.doc_id == existing.id))
                )
            )
            await session.execute(delete(Page).where(Page.doc_id == existing.id))
            await session.execute(delete(Document).where(Document.id == existing.id))
            await session.flush()

        document = Document(
            filename=doc_meta.filename,
            src_lang=src_lang,
            tgt_lang=tgt,
            status="ready_for_translation",
            created_at=datetime.now(UTC),
        )
        session.add(document)
        await session.flush()

        total_blocks = 0
        for page_doc in page_docs:
            png_path = extract_dir / "pages" / f"page_{page_doc.page_num:04d}.png"
            if not png_path.exists():
                raise IngestError(f"missing page image: {png_path.relative_to(extract_dir)}")
            page = Page(
                doc_id=document.id,
                page_num=page_doc.page_num,
                width=page_doc.width,
                height=page_doc.height,
                bg_image_path=str(png_path),
                rotation=page_doc.rotation,
                render_dpi=page_doc.render.dpi,
                pixel_width=page_doc.render.pixel_width,
                pixel_height=page_doc.render.pixel_height,
            )
            session.add(page)
            await session.flush()

            for block in page_doc.blocks:
                session.add(
                    Block(
                        page_id=page.id,
                        block_local_id=block.id,
                        type=block.type,
                        bbox_json=json.dumps(list(block.bbox)),
                        order_idx=block.order,
                        original_text=block.text,
                    )
                )
                total_blocks += 1
            await session.flush()

        return IngestStats(
            document_id=document.id,
            pages=len(page_docs),
            blocks=total_blocks,
        )
    except Exception:
        await session.rollback()
        raise


async def _require_schema_head(session: AsyncSession) -> None:
    version = await current_schema_version(session)
    if version != ALEMBIC_HEAD:
        msg_target = "missing alembic_version" if version is None else f"version {version!r}"
        raise SchemaVersionMismatch(
            f"DB schema mismatch ({msg_target}; head={ALEMBIC_HEAD!r}). "
            "Run: uv run alembic upgrade head"
        )


def _load_doc_meta(extract_dir: Path) -> DocMeta:
    meta_path = extract_dir / "doc_meta.json"
    if not meta_path.exists():
        raise IngestError(f"doc_meta.json missing in {extract_dir}")
    try:
        return DocMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise IngestError(f"doc_meta.json invalid: {exc}") from exc


def _resolve_src_lang(doc_meta: DocMeta, src_override: str | None) -> str:
    if src_override:
        return src_override
    if doc_meta.lang_guess in ("en", "ko"):
        return doc_meta.lang_guess
    raise IngestError(
        f"source language ambiguous (lang_guess={doc_meta.lang_guess!r}); " "pass --src explicitly"
    )


def _discover_page_files(extract_dir: Path, doc_meta: DocMeta) -> list[Path]:
    pages_dir = extract_dir / "pages"
    if not pages_dir.is_dir():
        raise IngestError(f"missing pages/ subdir in {extract_dir}")

    discovered: dict[int, Path] = {}
    for entry in sorted(pages_dir.iterdir()):
        m = PAGE_FILENAME_RE.match(entry.name)
        if not m:
            continue
        page_num = int(m.group(1))
        discovered[page_num] = entry

    if not discovered:
        raise IngestError(f"no page_*.json files under {pages_dir}")

    expected = set(range(1, doc_meta.num_pages + 1))
    found = set(discovered)
    missing = sorted(expected - found)
    extra = sorted(found - expected)
    if missing or extra:
        raise IngestError(
            f"page manifest mismatch in {pages_dir}: "
            f"missing={missing}, extra={extra}, "
            f"expected 1..{doc_meta.num_pages}"
        )
    return [discovered[i] for i in sorted(discovered)]


def _load_page_docs(page_files: list[Path]) -> list[PageDoc]:
    docs: list[PageDoc] = []
    for path in page_files:
        try:
            doc = PageDoc.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise IngestError(f"{path.name}: invalid page JSON: {exc}") from exc
        docs.append(doc)
    return docs


__all__ = ["IngestStats", "ingest_extract_dir"]
