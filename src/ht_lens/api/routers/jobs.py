"""``/jobs`` router — Phase 6d.

Frontend polls ``GET /jobs?status=active`` every 2 s while an upload is
running and shows the progress bar / message / error per job. Phase 6d
Planner-directed R2 fix added ``include_recent_terminals=true`` so the
panel can also surface ``failed`` (and recently ``done``) jobs — the
upload pipeline can fail at extract / translate / summarize, and the
user needs to see that error without having to check the DB by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ht_lens.api.deps import get_session
from ht_lens.api.schemas import JobRead
from ht_lens.db.models import Job
from ht_lens.jobs.pipeline import ACTIVE_STATUSES

router = APIRouter(tags=["jobs"])

# How long a terminal (done/failed) job remains visible in the
# "include_recent_terminals=true" feed. 5 minutes is enough for the user
# to read the error_message + dismiss it; older history lives at
# /jobs without filters.
TERMINAL_RECENT_WINDOW = timedelta(minutes=5)


@router.get("/jobs", response_model=list[JobRead])
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    include_recent_terminals: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JobRead]:
    """List jobs (newest first).

    - ``status=active`` returns every job currently in the
      pending → summarizing band.
    - ``status=<comma-separated>`` filters by literal statuses.
    - ``include_recent_terminals=true`` (Planner-directed R2 fix):
      stack on top of ``status=active`` and ALSO include ``failed`` /
      ``done`` rows whose ``finished_at`` is within the last
      ``TERMINAL_RECENT_WINDOW``. Lets the jobs panel surface a job
      that just failed (a previously invisible terminal state).
    """
    stmt = select(Job).order_by(Job.id.desc()).limit(limit)
    if status_filter == "active" and include_recent_terminals:
        cutoff = datetime.now(UTC) - TERMINAL_RECENT_WINDOW
        # Compare as naive UTC since Job.finished_at is stored naive.
        cutoff_naive = cutoff.replace(tzinfo=None)
        stmt = stmt.where(
            or_(
                Job.status.in_(ACTIVE_STATUSES),
                Job.finished_at.is_not(None) & (Job.finished_at >= cutoff_naive),
            )
        )
    elif status_filter == "active":
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
