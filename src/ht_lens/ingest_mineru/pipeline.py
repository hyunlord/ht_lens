"""Ingest a MinerU ``content_list.json`` into the 2.0 ``chunks`` schema (Phase 8a).

Creates one ``Document`` (``extractor='mineru'``) and one ``Chunk`` per
kept content_list item. Figure/chart images are copied out of MinerU's
output into ``data/extracts_v2/<doc_id>/images/`` and the chunk's
``img_path`` is rewritten to the managed absolute path.

Atomicity (challenge §3.2/§5.5): the caller owns commit; any failure here
rolls the session back AND removes the partial managed image directory, so
a half-ingested document never persists. Phase 8a deliberately does NOT
create ``pages`` rows (debate §2.1 — their render columns are NOT NULL;
side-by-side render is Phase 8c).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.db.models import Chunk, Document
from ht_lens.db.session import ALEMBIC_HEAD, current_schema_version
from ht_lens.errors import DocumentAlreadyIngested, IngestError, SchemaVersionMismatch
from ht_lens.ingest_mineru.content_list import ContentListError, parse_content_list

_log = logging.getLogger("ht_lens.ingest_mineru")

_DEFAULT_DEST_ROOT = Path("data/extracts_v2")


@dataclass(frozen=True)
class MineruIngestStats:
    document_id: int
    chunks: int
    images: int


async def ingest_mineru_output(
    content_list_path: Path,
    session: AsyncSession,
    *,
    filename: str,
    src: str = "en",
    tgt: str = "ko",
    images_dir: Path | None = None,
    markdown_path: Path | None = None,
    dest_root: Path = _DEFAULT_DEST_ROOT,
    overwrite: bool = False,
) -> MineruIngestStats:
    """Ingest the parsed ``content_list`` at ``content_list_path``.

    The caller owns transaction commit. On any failure the session is rolled
    back and partially-copied images are removed.
    """
    content_list_path = Path(content_list_path)
    if not content_list_path.is_file():
        raise IngestError(f"content_list.json not found: {content_list_path}")
    if images_dir is None:
        cand = content_list_path.parent / "images"
        images_dir = cand if cand.is_dir() else None

    await _require_schema_head(session)

    try:
        raw = json.loads(content_list_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError(f"cannot read content_list.json: {exc}") from exc
    try:
        parsed = parse_content_list(raw)
    except ContentListError as exc:
        raise IngestError(f"content_list.json invalid: {exc}") from exc
    if not parsed:
        raise IngestError("content_list.json yielded zero chunks (all chrome/empty?)")

    dest_dir: Path | None = None
    try:
        # Scope the collision lookup to MinerU-produced documents only
        # (verify-cross R1 §4): a 1.x ``pymupdf`` document with the same
        # filename must coexist untouched — the ``extractor`` column is
        # exactly what makes the parallel-DB decision safe. ``overwrite``
        # therefore can only ever replace a prior *mineru* ingest, never a
        # 1.x row, so "1.x DB 무손상" holds even on filename collision.
        existing = (
            await session.execute(
                select(Document).where(
                    Document.filename == filename,
                    Document.extractor == "mineru",
                )
            )
        ).scalar_one_or_none()
        if existing is not None and not overwrite:
            raise DocumentAlreadyIngested(
                f"MinerU document already ingested: {filename!r}. Use --overwrite to replace."
            )
        if existing is not None:
            # chunks cascade via delete-orphan when the Document is removed;
            # use explicit bulk delete to match the 1.x pattern. Scoped to
            # this mineru document id only — never a 1.x row.
            await session.execute(delete(Chunk).where(Chunk.doc_id == existing.id))
            await session.execute(delete(Document).where(Document.id == existing.id))
            await session.flush()

        document = Document(
            filename=filename,
            src_lang=src,
            tgt_lang=tgt,
            status="ready_for_translation",
            created_at=datetime.now(UTC),
            extractor="mineru",
            markdown_path=str(markdown_path) if markdown_path else None,
        )
        session.add(document)
        await session.flush()

        dest_dir = (dest_root / str(document.id) / "images").resolve()
        n_images = 0
        for pc in parsed:
            img_path_stored: str | None = None
            if pc.img_path:
                img_path_stored = _copy_image(pc.img_path, images_dir, dest_dir)
                n_images += 1
            session.add(
                Chunk(
                    doc_id=document.id,
                    page_idx=pc.page_idx,
                    order_idx=pc.order_idx,
                    type=pc.type,
                    text_level=pc.text_level,
                    bbox_json=pc.bbox_json,
                    content=pc.content,
                    text_format=pc.text_format,
                    img_path=img_path_stored,
                    caption=pc.caption,
                )
            )
        await session.flush()

        return MineruIngestStats(document_id=document.id, chunks=len(parsed), images=n_images)
    except Exception:
        await session.rollback()
        # Remove partially-copied managed images so a failed ingest leaves
        # no orphan files (the DB already rolled back).
        if dest_dir is not None and dest_dir.parent.exists():
            shutil.rmtree(dest_dir.parent, ignore_errors=True)
        raise


def _copy_image(rel_path: str, images_dir: Path | None, dest_dir: Path) -> str:
    """Copy a MinerU figure into the managed dir; return its absolute path.

    ``rel_path`` is MinerU-relative (e.g. ``images/abc.jpg``). The source is
    resolved against ``images_dir`` (the discovered ``.../auto/images``) by
    basename so layout differences don't matter. Missing source → raise
    (the caller rolls back — challenge §5.5)."""
    basename = Path(rel_path).name
    if images_dir is None:
        raise IngestError(f"chunk references image {rel_path!r} but no images dir was found")
    src = images_dir / basename
    if not src.is_file():
        raise IngestError(f"referenced image missing on disk: {src}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / basename
    shutil.copy2(src, dest)
    return str(dest)


async def _require_schema_head(session: AsyncSession) -> None:
    version = await current_schema_version(session)
    if version != ALEMBIC_HEAD:
        msg_target = "missing alembic_version" if version is None else f"version {version!r}"
        raise SchemaVersionMismatch(
            f"DB schema mismatch ({msg_target}; head={ALEMBIC_HEAD!r}). "
            "Run: uv run alembic upgrade head"
        )


__all__ = ["MineruIngestStats", "ingest_mineru_output"]
