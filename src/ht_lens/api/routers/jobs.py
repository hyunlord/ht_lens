"""``/jobs`` router — Phase 6d.

Frontend polls ``GET /jobs?status=active`` every 2 s while an upload is
running and shows the progress bar / message / error per job.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.api.deps import get_session
from ht_lens.api.schemas import JobRead
from ht_lens.db.models import Job
from ht_lens.jobs.pipeline import ACTIVE_STATUSES

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobRead])
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JobRead]:
    """List jobs (newest first). ``status=active`` returns every job
    currently in the pending → summarizing band; otherwise the value is
    parsed as a comma-separated set of literal statuses."""
    stmt = select(Job).order_by(Job.id.desc()).limit(limit)
    if status_filter == "active":
        stmt = stmt.where(Job.status.in_(ACTIVE_STATUSES))
    elif status_filter:
        wanted = [s.strip() for s in status_filter.split(",") if s.strip()]
        if wanted:
            stmt = stmt.where(Job.status.in_(wanted))
    rows = (await session.execute(stmt)).scalars().all()
    return [JobRead.model_validate(j) for j in rows]


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(
    job_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JobRead:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return JobRead.model_validate(job)
