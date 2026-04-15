#======================================================================================================
# Endpoints for fetching job logs and streaming them in real-time via WebSocket.
#======================================================================================================

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_database_manager, get_db_session
from backend.api.schemas import LogEntryListResponse, LogEntryResponse
from backend.src.managers.database_manager import DatabaseManager
from backend.src.models import LogLevel
from backend.database.connection import async_session_factory
from backend.logging_config import get_logger

router = APIRouter()
logger = get_logger("logs_endpoint")


@router.get("/{job_id}", response_model=LogEntryListResponse)
async def get_logs(
    job_id: uuid.UUID,
    level: str | None = Query(None, description="Filter by log level"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    db: DatabaseManager = Depends(get_database_manager),
) -> LogEntryListResponse:
    """Fetch stored log entries for a job."""
    job = await db.get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    log_level = None
    if level:
        try:
            log_level = LogLevel(level.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid log level: {level}. Valid: {[l.value for l in LogLevel]}"
            )

    entries = await db.get_log_entries(
        session, job_id, level=log_level, limit=limit, offset=offset
    )
    total = await db.count_log_entries(session, job_id)

    return LogEntryListResponse(
        entries=[LogEntryResponse.model_validate(e) for e in entries],
        total=total,
    )


@router.websocket("/ws/{job_id}")
async def log_stream(
    websocket: WebSocket,
    job_id: uuid.UUID,
) -> None:
    """
    Stream live log entries for a job.
    """
    await websocket.accept()

    db = DatabaseManager()

    try:
        # Initialize last_seen_count to current count so only stream NEW entries written after this WebSocket connection was established.
        # This prevents duplicating entries already loaded via the REST endpoint. P
        async with async_session_factory() as session:
            last_seen_count = await db.count_log_entries(session, job_id)

        while True:
            async with async_session_factory() as session:
                current_count = await db.count_log_entries(session, job_id)

                if current_count > last_seen_count:
                    new_count = current_count - last_seen_count
                    entries = await db.get_log_entries(
                        session, job_id, limit=new_count, offset=0
                    )

                    # Entries come newest-first, reverse to send oldest first
                    for entry in reversed(list(entries)):
                        message = {
                            "id": str(entry.id),
                            "level": entry.level.value,
                            "message": entry.message,
                            "source_url": entry.source_url,
                            "component": entry.component,
                            "created_at": entry.created_at.isoformat(),
                        }
                        await websocket.send_text(json.dumps(message))

                    last_seen_count = current_count

                # Send live status update every poll cycle
                job = await db.get_job(session, job_id)
                if job:
                    status_msg = {
                        "type": "status_update",
                        "status": job.status.value,
                        "pages_scraped": job.pages_scraped,
                        "pages_failed": job.pages_failed,
                        "total_pages_discovered": job.total_pages_discovered,
                        "pages_per_second": job.pages_per_second,
                    }
                    await websocket.send_text(json.dumps(status_msg))

                    if job.status.value in ("completed", "failed", "stopped"):
                        # Job is done — do one final poll after a short delay to pick up any log entries written in the same
                        # window as the status flip (e.g., "Classified as:", "Job finished:"). 
                        # Without this delay, those entries arrive in DB milliseconds after we already checked.
                        await asyncio.sleep(1.5)

                        async with async_session_factory() as final_session:
                            final_count = await db.count_log_entries(
                                final_session, job_id
                            )

                            if final_count > last_seen_count:
                                new_count = final_count - last_seen_count
                                final_entries = await db.get_log_entries(
                                    final_session, job_id,
                                    limit=new_count, offset=0
                                )
                                for entry in reversed(list(final_entries)):
                                    message = {
                                        "id": str(entry.id),
                                        "level": entry.level.value,
                                        "message": entry.message,
                                        "source_url": entry.source_url,
                                        "component": entry.component,
                                        "created_at": entry.created_at.isoformat(),
                                    }
                                    await websocket.send_text(
                                        json.dumps(message)
                                    )

                        # Now send the terminal job_finished message
                        final_msg = {
                            "type": "job_finished",
                            "status": job.status.value,
                        }
                        await websocket.send_text(json.dumps(final_msg))
                        break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("websocket_disconnected", job_id=str(job_id))
    except Exception as exc:
        logger.error("websocket_error", job_id=str(job_id), error=str(exc))
        try:
            await websocket.close(code=1011, reason=str(exc)[:120])
        except Exception:
            pass
