"""Upload job pipeline — Phase 6d.

``process_upload_job(job_id, app)`` drives the upload through the
linear status machine:

    pending → extracting → ingesting → translating → summarizing → done

``failed`` is entered when any stage raises. Each stage owns its own
short-lived ``AsyncSession`` (challenge §2 boundary fix) so progress
updates can't be rolled back by a downstream failure.

Blocking work (``extract_pdf`` is sync PyMuPDF) is wrapped with
``asyncio.to_thread`` so the running event loop keeps serving
``GET /jobs`` polling traffic while extraction is in progress
(debate §2 critical fix).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ht_lens.db.models import Job
from ht_lens.extract.pipeline import extract_pdf
from ht_lens.ingest.pipeline import ingest_extract_dir
from ht_lens.llm.client import LLMClient
from ht_lens.summarize.pipeline import SummarizeEmptyError, summarize_document
from ht_lens.translate.pipeline import translate_document

if TYPE_CHECKING:  # avoid circular import at runtime
    from fastapi import FastAPI

_log = logging.getLogger("ht_lens.jobs")

# Linear status machine.
JOB_STATUSES: tuple[str, ...] = (
    "pending",
    "extracting",
    "ingesting",
    "translating",
    "summarizing",
    "done",
    "failed",
)
ACTIVE_STATUSES: tuple[str, ...] = (
    "pending",
    "extracting",
    "ingesting",
    "translating",
    "summarizing",
)


async def update_job(
    factory: async_sessionmaker[AsyncSession],
    job_id: int,
    *,
    status: str | None = None,
    document_id: int | None = None,
    progress_pct: int | None = None,
    progress_message: str | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    """Apply a partial update to ``jobs.id`` in its own short transaction.

    Phase 6d challenge §2 fix: every progress write uses its own session so
    a translate failure rolling back its session cannot wipe the progress
    rows we already wrote. ``factory`` is the lifespan-owned
    ``async_sessionmaker`` passed in by the caller.
    """
    async with factory() as session:
        job = await session.get(Job, job_id)
        if job is None:
            _log.warning("update_job: job %s not found", job_id)
            return
        if status is not None:
            job.status = status
        if document_id is not None:
            job.document_id = document_id
        if progress_pct is not None:
            job.progress_pct = max(0, min(100, progress_pct))
        if progress_message is not None:
            job.progress_message = progress_message
        if error_message is not None:
            job.error_message = error_message
        if started_at is not None:
            job.started_at = started_at
        if finished_at is not None:
            job.finished_at = finished_at
        await session.commit()


async def process_upload_job(job_id: int, app: FastAPI) -> None:
    """Drive a single upload job from ``pending`` to ``done`` (or
    ``failed``). All blocking work is offloaded to a worker thread so
    other async traffic (e.g. ``GET /jobs`` polling) stays responsive
    while extraction runs.
    """
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    llm: LLMClient = app.state.llm

    try:
        await update_job(
            factory,
            job_id,
            status="extracting",
            progress_pct=5,
            progress_message="PDF 추출 준비",
            started_at=datetime.now(UTC),
        )

        # --- Load job context (upload path + filename) ---
        async with factory() as session:
            job = await session.get(Job, job_id)
            if job is None:
                _log.error("process_upload_job: job %s vanished", job_id)
                return
            upload_path = Path(job.upload_path) if job.upload_path else None
            display_filename = job.upload_filename or "unknown.pdf"
            upload_sha256 = job.upload_sha256
        if upload_path is None or not upload_path.is_file():
            raise FileNotFoundError(f"upload file not found: {upload_path!r}")

        # --- Extract (sync PyMuPDF + Pillow → run in worker thread) ---
        extracts_root = upload_path.parent.parent / "extracts"
        extract_dir = extracts_root / (upload_sha256 or upload_path.stem)
        if extract_dir.exists():
            # Restart-recovery cleanup: an in-flight job that we marked
            # failed at startup may have left a partial extract dir.
            shutil.rmtree(extract_dir)
        extract_dir.parent.mkdir(parents=True, exist_ok=True)
        await update_job(
            factory,
            job_id,
            progress_pct=10,
            progress_message=f"PDF 추출 중: {display_filename}",
        )
        await asyncio.to_thread(extract_pdf, upload_path, extract_dir)
        await update_job(
            factory,
            job_id,
            status="ingesting",
            progress_pct=25,
            progress_message="DB 적재 중",
        )

        # --- Ingest (own session + own transaction) ---
        document_id: int | None = None
        async with factory() as session:
            stats = await ingest_extract_dir(
                extract_dir,
                session,
                src=None,
                tgt="ko",
                overwrite=True,
                display_filename_override=display_filename,
            )
            document_id = stats.document_id
            await session.commit()
        await update_job(
            factory,
            job_id,
            status="translating",
            document_id=document_id,
            progress_pct=30,
            progress_message="번역 시작",
        )

        # --- Translate (own session, callback to update progress) ---
        async def _on_progress(done: int, total: int) -> None:
            # Map block progress into the 30~90 percentage band so the
            # surrounding stages still show up in the bar.
            pct = 30 + int(60 * (done / total)) if total else 30
            await update_job(
                factory,
                job_id,
                progress_pct=pct,
                progress_message=f"번역 중 {done}/{total}",
            )

        async with factory() as session:
            await translate_document(
                document_id,
                session,
                llm,
                on_progress=_on_progress,
            )

        # --- Summarize (own session). Empty body is non-fatal — done with
        # a clear error_message so the viewer can still load. ---
        await update_job(
            factory,
            job_id,
            status="summarizing",
            progress_pct=92,
            progress_message="요약 생성 중",
        )
        summary_error: str | None = None
        try:
            async with factory() as session:
                summary = await summarize_document(document_id, session, llm)
                from ht_lens.db.models import Document  # local to avoid cycle

                doc = await session.get(Document, document_id)
                if doc is not None:
                    doc.summary = summary
                    doc.summarized_at = datetime.now(UTC)
                await session.commit()
        except SummarizeEmptyError as exc:
            summary_error = str(exc)
            _log.info("job %s summarize skipped: %s", job_id, exc)
        except Exception as exc:  # non-fatal stage — log and continue
            summary_error = f"요약 실패: {exc}"
            _log.warning("job %s summarize failed: %s", job_id, exc)

        await update_job(
            factory,
            job_id,
            status="done",
            progress_pct=100,
            progress_message="완료",
            error_message=summary_error,
            finished_at=datetime.now(UTC),
        )
    except Exception as exc:  # top-level fatal handler — mark job failed
        _log.exception("job %s failed", job_id)
        await update_job(
            factory,
            job_id,
            status="failed",
            error_message=str(exc),
            finished_at=datetime.now(UTC),
        )


async def mark_in_flight_jobs_failed(factory: async_sessionmaker[AsyncSession]) -> int:
    """On startup, any job left in an active status is leftover from a
    previous server run (we don't survive restarts). Mark them ``failed``
    so polling clients see a definitive terminal state.

    Returns the number of rows updated.
    """
    async with factory() as session:
        rows = (
            (await session.execute(select(Job).where(Job.status.in_(ACTIVE_STATUSES))))
            .scalars()
            .all()
        )
        now = datetime.now(UTC)
        for job in rows:
            job.status = "failed"
            job.error_message = "서버 재시작으로 중단됨"
            if job.finished_at is None:
                job.finished_at = now
        await session.commit()
        return len(rows)
