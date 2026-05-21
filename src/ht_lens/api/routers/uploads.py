"""``POST /uploads`` — Phase 6d PDF ingest entrypoint.

Streams the uploaded file to a temp path inside ``data/uploads/`` (same
filesystem as the final destination so rename is atomic — debate §3
EXDEV fix), enforces a 100 MB cap, sha256-hashes the content, and
either returns the existing document (dedup) or spawns a background
job that drives the extract → ingest → translate → summarize pipeline.

Concurrent-same-sha race (debate §3 critical fix):
the read-before-write dedup query in this router can race with another
upload. The migration-0003 UNIQUE constraint on
``documents.src_pdf_sha256`` is the authoritative guarantee — the
INSERT in the ingest stage will raise ``IntegrityError`` on a collision
and the job is marked failed. The router itself also catches the
race-window dedup hit and returns the existing document.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.api.deps import get_session
from ht_lens.api.schemas import UploadResponse
from ht_lens.db.models import Document, Job
from ht_lens.jobs.pipeline import ACTIVE_STATUSES, process_upload_job

router = APIRouter(tags=["uploads"])

# 100 MB; tuned for v0.7 single-user use. Anything larger needs Phase 6e
# streaming + chunked progress, not 6d's load-once-then-process flow.
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

_FILENAME_ALLOWED = re.compile(r"[^\w\s.\-가-힣]+")
_log = logging.getLogger("ht_lens.api.uploads")


def sanitize_filename(name: str) -> str:
    """Strip directory components and disallowed characters from a user
    filename so it's safe to store in ``documents.filename`` and display
    in the UI. Keeps Korean characters intact."""
    base = Path(name).name or "unknown.pdf"
    base = _FILENAME_ALLOWED.sub("_", base)
    return base[:200] or "unknown.pdf"


def _hash_chunk_sync(chunks: list[bytes]) -> str:
    """Pure-Python hashlib loop wrapped in ``asyncio.to_thread`` by the
    caller — debate §2 fix to keep the event loop free during the
    upload itself."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.hexdigest()


async def _stream_to_tmp(
    file: UploadFile, uploads_dir: Path, max_bytes: int
) -> tuple[Path, str, int]:
    """Read ``file`` into a temp file inside ``uploads_dir`` (same fs as
    the final destination — debate §3 EXDEV fix), return
    ``(tmp_path, sha256_hex, total_bytes)``. Raises 413 on overflow."""
    h = hashlib.sha256()
    total = 0
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 — file lives past the function (returned path)
        dir=uploads_dir, prefix=".upload-", suffix=".pdf", delete=False
    )
    try:
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"파일이 {max_bytes // (1024 * 1024)}MB 제한을 초과했습니다",
                )
            h.update(chunk)
            tmp.write(chunk)
    finally:
        tmp.close()
    return Path(tmp.name), h.hexdigest(), total


@router.post(
    "/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_pdf(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UploadResponse:
    # 1. Magic-byte sanity check before allocating temp storage.
    head = await file.read(5)
    if head != b"%PDF-":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="PDF 파일만 업로드 가능합니다 (매직 바이트 불일치)",
        )
    await file.seek(0)

    uploads_dir: Path = request.app.state.uploads_dir
    # 2. Stream-hash to a temp path on the same filesystem.
    tmp_path, sha256, total = await _stream_to_tmp(file, uploads_dir, MAX_UPLOAD_BYTES)

    # 3. Read-before-write dedup. The DB UNIQUE constraint is authoritative;
    #    this is just a fast-path that avoids spawning a redundant job.
    existing = await session.scalar(select(Document).where(Document.src_pdf_sha256 == sha256))
    if existing is not None:
        tmp_path.unlink(missing_ok=True)
        return UploadResponse(job_id=None, document_id=existing.id, dedup=True)

    # 3b. R1 fix (cross-verify §4): also reuse any active job for the same
    # sha256. The race window between "file already on disk" and "Document
    # row committed" is exactly when a second upload arrives — return the
    # in-flight job id instead of spawning a redundant one.
    active_job = await session.scalar(
        select(Job)
        .where(Job.upload_sha256 == sha256)
        .where(Job.status.in_(ACTIVE_STATUSES))
        .order_by(Job.id.desc())
    )
    if active_job is not None:
        tmp_path.unlink(missing_ok=True)
        return UploadResponse(job_id=active_job.id, document_id=None, dedup=True)

    # 4. Atomic rename into final {sha256}.pdf slot (same fs, so safe).
    final_path = uploads_dir / f"{sha256}.pdf"
    if final_path.exists():
        # File exists but no active job + no Document — leftover from a
        # crash. Reuse the file; treat the upload as a fresh job (we'll
        # spawn process_upload_job below which calls extract with
        # ``overwrite=True`` on the extract dir to clean any partial
        # extract artefacts).
        tmp_path.unlink(missing_ok=True)
    else:
        tmp_path.rename(final_path)

    # 5. Create the job row + spawn the background task.
    display_filename = sanitize_filename(file.filename or "unknown.pdf")
    job = Job(
        type="process_upload",
        status="pending",
        upload_path=str(final_path),
        upload_filename=display_filename,
        upload_sha256=sha256,
        progress_pct=0,
        progress_message="대기 중",
        created_at=__import__("datetime").datetime.utcnow(),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    bg_tasks: set[asyncio.Task[None]] = request.app.state.background_tasks
    task = asyncio.create_task(process_upload_job(job.id, request.app))
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)

    _log.info("upload accepted job_id=%s sha256=%s bytes=%s", job.id, sha256, total)
    return UploadResponse(job_id=job.id, document_id=None, dedup=False)
