# =============================================================================
# Endpoints for viewing scrape results and content version history.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_database_manager, get_db_session
from backend.api.schemas import (
    ContentVersionResponse,
    ScrapeResultListResponse,
    ScrapeResultResponse,
)
from backend.src.managers.database_manager import DatabaseManager

router = APIRouter()


@router.get("/{job_id}/results", response_model=ScrapeResultListResponse)
async def list_scrape_results(
    job_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> ScrapeResultListResponse:
    """List scrape results for a specific job."""
    # Verify job exists
    job = await db.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    results = await db.get_scrape_results(session, job_id, limit=limit, offset=offset)

    return ScrapeResultListResponse(
        results=[ScrapeResultResponse.model_validate(r) for r in results],
        total=len(results),
    )


@router.get("/versions", response_model=list[ContentVersionResponse])
async def get_content_versions(
    url: str = Query(..., description="URL to get version history for"),
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> list[ContentVersionResponse]:
    """Get the content version history for a specific URL."""
    versions = await db.get_content_versions(session, url)

    if not versions:
        raise HTTPException(
            status_code=404,
            detail="No content versions found for this URL"
        )

    return [ContentVersionResponse.model_validate(v) for v in versions]
