#======================================================================================================
# Analytics endpoints
#======================================================================================================

from __future__ import annotations

import csv
import io
import json
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_database_manager, get_db_session
from backend.src.managers.database_manager import DatabaseManager

router = APIRouter()


#----------------------------------------------------------------------------------------------------
# Local response schemas
# (defined here to match exactly what DatabaseManager actually returns)
class StatsResponse(BaseModel):
    """Overall scraping statistics."""
    total_jobs: int = 0
    running_jobs: int = 0
    total_pages_scraped: int = 0
    total_content_versions: int = 0
    total_errors: int = 0


class VolumeEntry(BaseModel):
    """A single day's scrape count."""
    date: str
    count: int


class CategoryEntry(BaseModel):
    """Result count per category."""
    category: str
    count: int


#----------------------------------------------------------------------------------------------------
# Endpoints
@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> StatsResponse:
    """Get overall scraping statistics."""
    stats = await db.get_stats(session)
    return StatsResponse(**stats)


@router.get("/volume", response_model=List[VolumeEntry])
async def get_volume(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> List[VolumeEntry]:
    """Get daily scrape volume over the last N days."""
    data = await db.get_scrape_volume(session, days=days)
    return [VolumeEntry(**entry) for entry in data]


@router.get("/categories", response_model=List[CategoryEntry])
async def get_category_distribution(
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> List[CategoryEntry]:
    """Get scrape result count per category."""
    data = await db.get_category_distribution(session)
    return [CategoryEntry(**entry) for entry in data]


@router.get("/export/{job_id}")
async def export_results(
    job_id: uuid.UUID,
    format: str = Query("json", description="Export format: json or csv"),
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> StreamingResponse:
    """Export scrape results for a job as JSON or CSV."""
    job = await db.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    results = await db.get_scrape_results(session, job_id, limit=10000)

    if format.lower() == "csv":
        return _export_csv(results, job_id)
    else:
        return _export_json(results, job_id)


def _export_json(results, job_id: uuid.UUID) -> StreamingResponse:
    """Generate a JSON export of scrape results."""
    export_data = []
    for result in results:
        export_data.append({
            "url": result.url,
            "http_status": result.http_status,
            "page_title": result.page_title,
            "content": result.content,
            "content_length": result.content_length,
            "error": result.error,
            "scraped_at": result.created_at.isoformat() if result.created_at else None,
        })

    json_str = json.dumps(export_data, indent=2, ensure_ascii=False)

    return StreamingResponse(
        io.BytesIO(json_str.encode("utf-8")),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=scrape_results_{job_id}.json"
        },
    )


def _export_csv(results, job_id: uuid.UUID) -> StreamingResponse:
    """Generate a CSV export of scrape results."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "url", "http_status", "page_title",
        "content_length", "error", "scraped_at",
    ])

    for result in results:
        writer.writerow([
            result.url,
            result.http_status or "",
            result.page_title or "",
            result.content_length,
            result.error or "",
            result.created_at.isoformat() if result.created_at else "",
        ])

    csv_bytes = output.getvalue().encode("utf-8")

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=scrape_results_{job_id}.csv"
        },
    )
