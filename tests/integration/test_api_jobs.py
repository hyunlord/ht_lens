"""Phase 6d — /jobs router."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from ht_lens.db.models import Job
from ht_lens.db.session import make_engine, make_session_factory

from ._api_helpers import make_test_client


async def _seed_jobs(db_path: Path, *jobs: dict) -> list[int]:
    """Seed jobs AFTER lifespan startup (which marks active jobs failed
    on restart-recovery). Caller should invoke this from inside the
    ``make_test_client`` block."""
    engine = make_engine(db_path)
    factory = make_session_factory(engine)
    ids: list[int] = []
    async with factory() as session:
        for spec in jobs:
            job = Job(
                type=spec.get("type", "process_upload"),
                status=spec["status"],
                progress_pct=spec.get("progress_pct", 0),
                upload_filename=spec.get("upload_filename"),
                upload_sha256=spec.get("upload_sha256"),
                created_at=datetime.utcnow(),
            )
            session.add(job)
            await session.flush()
            ids.append(job.id)
        await session.commit()
    await engine.dispose()
    return ids


@pytest.mark.asyncio
async def test_get_jobs_returns_empty_when_none(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_jobs_lists_newest_first(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        ids = await _seed_jobs(
            api_db_path,
            {"status": "done", "upload_filename": "a.pdf"},
            {"status": "translating", "upload_filename": "b.pdf"},
            {"status": "failed", "upload_filename": "c.pdf"},
        )
        resp = client.get("/jobs")
    body = resp.json()
    assert [j["id"] for j in body] == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_get_jobs_active_filter(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        await _seed_jobs(
            api_db_path,
            {"status": "done"},
            {"status": "translating"},
            {"status": "summarizing"},
            {"status": "failed"},
        )
        resp = client.get("/jobs?status=active")
    body = resp.json()
    statuses = sorted(j["status"] for j in body)
    assert statuses == ["summarizing", "translating"]


@pytest.mark.asyncio
async def test_get_jobs_explicit_status_filter(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        await _seed_jobs(
            api_db_path,
            {"status": "done"},
            {"status": "failed"},
            {"status": "translating"},
        )
        resp = client.get("/jobs?status=done,failed")
    statuses = sorted(j["status"] for j in resp.json())
    assert statuses == ["done", "failed"]


@pytest.mark.asyncio
async def test_get_job_by_id_404(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        resp = client.get("/jobs/9999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_job_by_id_returns_details(api_db_path: Path) -> None:
    with make_test_client(api_db_path) as client:
        [job_id] = await _seed_jobs(
            api_db_path,
            {
                "status": "translating",
                "progress_pct": 42,
                "upload_filename": "demo.pdf",
                "upload_sha256": "f" * 64,
            },
        )
        resp = client.get(f"/jobs/{job_id}")
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "translating"
    assert body["progress_pct"] == 42
    assert body["upload_filename"] == "demo.pdf"


@pytest.mark.asyncio
async def test_startup_marks_active_jobs_failed(api_db_path: Path) -> None:
    """Debate §5 missing test: a job left in an active status from a
    previous server run must be terminated on the next lifespan startup."""
    # Seed an "active" job BEFORE lifespan runs.
    await _seed_jobs(
        api_db_path,
        {"status": "translating", "upload_filename": "orphan.pdf"},
    )
    with make_test_client(api_db_path) as client:
        resp = client.get("/jobs")
    body = resp.json()
    assert len(body) == 1
    job = body[0]
    assert job["status"] == "failed"
    assert "재시작" in (job["error_message"] or "")


@pytest.mark.asyncio
async def test_startup_recovery_deletes_partial_documents(
    api_db_path: Path, tmp_path: Path
) -> None:
    """R1 fix (cross-verify §4): when restart-recovery marks an active
    job failed, the half-ingested document it pointed at must also be
    cleaned up. Otherwise the upload-router sha256 dedup routes the
    next upload of the same file back to the ghost document instead
    of starting fresh."""
    from ht_lens.db.models import Document, Job
    from ht_lens.db.session import make_engine, make_session_factory

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        # Insert a half-ingested Document (status="ready_for_translation").
        doc = Document(
            filename="partial.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="ready_for_translation",
            src_pdf_sha256="d" * 64,
            created_at=datetime.utcnow(),
        )
        session.add(doc)
        await session.flush()
        # Insert an active job pointing at it.
        job = Job(
            type="process_upload",
            status="translating",
            document_id=doc.id,
            upload_filename="partial.pdf",
            upload_sha256="d" * 64,
            progress_pct=50,
            created_at=datetime.utcnow(),
        )
        session.add(job)
        await session.commit()
        doc_id = doc.id
    await engine.dispose()

    # Lifespan should clean up: job → failed, document → deleted.
    with make_test_client(api_db_path) as client:
        jobs_resp = client.get("/jobs")
        docs_resp = client.get("/documents")
    job_rows = jobs_resp.json()
    assert len(job_rows) == 1 and job_rows[0]["status"] == "failed"
    assert job_rows[0]["document_id"] is None  # pointer nulled
    docs = docs_resp.json()
    assert all(d["id"] != doc_id for d in docs), (
        "partial document should be deleted by restart recovery"
    )


@pytest.mark.asyncio
async def test_startup_recovery_preserves_translated_documents(
    api_db_path: Path,
) -> None:
    """A failed summarize stage finishes the job ``done`` with an error,
    but the document is fully translated and should survive future
    restarts cleanly."""
    from ht_lens.db.models import Document, Job
    from ht_lens.db.session import make_engine, make_session_factory

    engine = make_engine(api_db_path)
    factory = make_session_factory(engine)
    async with factory() as session:
        doc = Document(
            filename="finished.pdf",
            src_lang="en",
            tgt_lang="ko",
            status="translated",
            src_pdf_sha256="e" * 64,
            created_at=datetime.utcnow(),
        )
        session.add(doc)
        await session.flush()
        # Active job pointing at a translated doc — pretend the summarize
        # stage was running when the server died.
        job = Job(
            type="process_upload",
            status="summarizing",
            document_id=doc.id,
            upload_filename="finished.pdf",
            upload_sha256="e" * 64,
            progress_pct=92,
            created_at=datetime.utcnow(),
        )
        session.add(job)
        await session.commit()
        doc_id = doc.id
    await engine.dispose()

    with make_test_client(api_db_path) as client:
        docs = client.get("/documents").json()
    # Translated doc survives the restart sweep.
    assert any(d["id"] == doc_id for d in docs)


# --- Planner-directed R2 fix: failed jobs surfaced in poll ---


@pytest.mark.asyncio
async def test_jobs_active_plus_recent_terminals_includes_failed(
    api_db_path: Path,
) -> None:
    """R2 fix: ``include_recent_terminals=true`` surfaces failed/done
    jobs from the last 5 minutes alongside active ones. Without this,
    a job that failed at extract/translate/summarize disappeared from
    the panel and the user never saw the error_message."""
    from ht_lens.db.models import Job
    from ht_lens.db.session import make_engine, make_session_factory

    with make_test_client(api_db_path) as client:
        # Seed three jobs inside the client lifespan to bypass the
        # startup-recovery sweep on the "translating" row.
        engine = make_engine(api_db_path)
        factory = make_session_factory(engine)
        async with factory() as session:
            now = datetime.utcnow()
            session.add(
                Job(
                    type="process_upload",
                    status="failed",
                    upload_filename="just_failed.pdf",
                    error_message="요약 실패: timeout",
                    finished_at=now,
                    created_at=now,
                )
            )
            session.add(
                Job(
                    type="process_upload",
                    status="done",
                    upload_filename="just_done.pdf",
                    finished_at=now,
                    created_at=now,
                )
            )
            session.add(
                Job(
                    type="process_upload",
                    status="translating",
                    upload_filename="still_running.pdf",
                    progress_pct=40,
                    created_at=now,
                )
            )
            # Older failed (10 min ago) — must NOT appear in the recent
            # window response.
            from datetime import timedelta

            session.add(
                Job(
                    type="process_upload",
                    status="failed",
                    upload_filename="old_failed.pdf",
                    finished_at=now - timedelta(minutes=10),
                    created_at=now - timedelta(minutes=10),
                )
            )
            await session.commit()
        await engine.dispose()

        # Without the flag: only the active job is returned.
        body_active = client.get("/jobs?status=active").json()
        names_active = sorted(j["upload_filename"] for j in body_active)
        assert names_active == ["still_running.pdf"]

        # With the flag: active + recent terminals, but not old ones.
        body_full = client.get("/jobs?status=active&include_recent_terminals=true").json()
        names_full = sorted(j["upload_filename"] for j in body_full)
        assert names_full == ["just_done.pdf", "just_failed.pdf", "still_running.pdf"]


@pytest.mark.asyncio
async def test_jobs_recent_terminals_carries_error_message(
    api_db_path: Path,
) -> None:
    """R2 fix sanity: the error_message field flows through the new
    query path so the panel can render it."""
    from ht_lens.db.models import Job
    from ht_lens.db.session import make_engine, make_session_factory

    with make_test_client(api_db_path) as client:
        engine = make_engine(api_db_path)
        factory = make_session_factory(engine)
        async with factory() as session:
            now = datetime.utcnow()
            session.add(
                Job(
                    type="process_upload",
                    status="failed",
                    upload_filename="boom.pdf",
                    error_message="PDF 추출 실패: invalid stream",
                    finished_at=now,
                    created_at=now,
                )
            )
            await session.commit()
        await engine.dispose()

        body = client.get("/jobs?status=active&include_recent_terminals=true").json()
    assert len(body) == 1
    assert body[0]["status"] == "failed"
    assert body[0]["error_message"] == "PDF 추출 실패: invalid stream"
