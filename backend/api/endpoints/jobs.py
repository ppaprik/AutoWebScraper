#======================================================================================================
# CRUD endpoints for scraping jobs plus control actions (pause/resume/stop).
#======================================================================================================

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_database_manager, get_db_session
from backend.api.schemas import (
    JobActionRequest,
    JobCreate,
    JobListResponse,
    JobResponse,
    MessageResponse,
)
from backend.src.managers.database_manager import DatabaseManager
from backend.src.models import JobStatus

router = APIRouter()


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> JobResponse:
    """Create a new scraping job and queue it for execution."""
    url_rules = None
    if body.url_rules:
        url_rules = [rule.model_dump() for rule in body.url_rules]

    # Convert filter_category_ids from UUID objects to plain strings for JSON storage.
    filter_category_ids = None
    if body.filter_category_ids:
        filter_category_ids = [str(cid) for cid in body.filter_category_ids]

    job = await db.create_job(
        session=session,
        name=body.name,
        start_url=body.start_url,
        crawl_mode=body.crawl_mode,
        url_rules=url_rules,
        data_targets=body.data_targets,
        category_id=body.category_id,
        filter_category_ids=filter_category_ids,
        credential_id=body.credential_id,
        js_mode=body.js_mode.value if hasattr(body.js_mode, "value") else str(body.js_mode),
    )

    # Queue the job as a Celery task
    from backend.tasks.scrape_tasks import execute_scrape_job
    task = execute_scrape_job.delay(str(job.id))

    # Store the Celery task ID on the job
    await db.update_job_status(
        session, job.id, JobStatus.PENDING, celery_task_id=task.id
    )

    return JobResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> JobListResponse:
    """List all jobs with optional status filter."""
    job_status = None
    if status:
        try:
            job_status = JobStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in JobStatus]}",
            )

    jobs = await db.list_jobs(session, status=job_status, limit=limit, offset=offset)
    total = await db.count_jobs(session, status=job_status)
    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs],
        total=total,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> JobResponse:
    """Get a single job by ID."""
    job = await db.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.post("/{job_id}/action", response_model=MessageResponse)
async def job_action(
    job_id: uuid.UUID,
    body: JobActionRequest,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> MessageResponse:
    """Execute a control action (pause/resume/stop) on a job."""
    job = await db.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    from backend.src.managers.thread_manager import ThreadManager
    thread_manager = ThreadManager()

    if body.action == "pause":
        if job.status != JobStatus.RUNNING:
            raise HTTPException(status_code=400, detail="Job is not running")
        thread_manager.send_pause_signal(str(job_id))
        await db.update_job_status(session, job_id, JobStatus.PAUSED)
        return MessageResponse(message="Job paused")

    elif body.action == "resume":
        if job.status != JobStatus.PAUSED:
            raise HTTPException(status_code=400, detail="Job is not paused")
        thread_manager.send_resume_signal(str(job_id))
        await db.update_job_status(session, job_id, JobStatus.RUNNING)
        return MessageResponse(message="Job resumed")

    elif body.action == "stop":
        if job.status not in (JobStatus.RUNNING, JobStatus.PAUSED):
            raise HTTPException(status_code=400, detail="Job is not active")
        thread_manager.send_stop_signal(str(job_id))
        await db.update_job_status(session, job_id, JobStatus.STOPPED)
        return MessageResponse(message="Job stopped")

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action '{body.action}'. Valid actions: pause, resume, stop",
        )


@router.delete("/{job_id}", response_model=MessageResponse)
async def delete_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> MessageResponse:
    """Delete a job and all its associated data."""
    job = await db.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Stop the job first if it is still running
    if job.status in (JobStatus.RUNNING, JobStatus.PAUSED):
        from backend.src.managers.thread_manager import ThreadManager
        ThreadManager().send_stop_signal(str(job_id))

    deleted = await db.delete_job(session, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")

    return MessageResponse(message="Job deleted")
