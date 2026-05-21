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
