#======================================================================================================
# Celery task definitions for scraping operations.
# Each task runs in its own worker process (prefork pool).
# The ThreadManager bridges into asyncio for concurrent HTTP I/O.
#======================================================================================================

from __future__ import annotations

import uuid

from celery import Task
from celery.utils.log import get_task_logger

from backend.tasks.celery_app import celery_app

task_logger = get_task_logger(__name__)


class ScrapeTask(Task):
    """
    Base task class with error handling and cleanup.
    Provides automatic retry and failure logging.
    """

    autoretry_for = (ConnectionError, TimeoutError)
    retry_kwargs = {"max_retries": 2, "countdown": 10}
    retry_backoff = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when a task fails after all retries."""
        job_id = args[0] if args else "unknown"
        task_logger.error(
            "Task failed permanently: job_id=%s error=%s",
            job_id,
            str(exc),
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Called when a task completes successfully."""
        job_id = args[0] if args else "unknown"
        task_logger.info(
            "Task completed: job_id=%s result=%s",
            job_id,
            retval,
        )


@celery_app.task(
    base=ScrapeTask,
    bind=True,
    name="backend.tasks.scrape_tasks.execute_scrape_job",
)
def execute_scrape_job(self, job_id_str: str) -> dict:
    """
    Execute a scraping job. This is the main entry point called by the API
    when a new job is created.

    Runs inside a Celery worker process. The ThreadManager creates an asyncio
    event loop and runs the ScraperManager within it.

    Args:
        job_id_str: String representation of the job UUID.

    Returns:
        Summary dict with pages_scraped, pages_failed, etc.
    """
    from backend.src.managers.thread_manager import ThreadManager

    job_id = uuid.UUID(job_id_str)
    task_logger.info("Starting scrape job: %s", job_id_str)

    thread_mgr = ThreadManager()

    try:
        result = thread_mgr.execute_job(job_id)
        return result
    except Exception as exc:
        task_logger.error("Scrape job failed: %s — %s", job_id_str, str(exc))
        raise
    finally:
        thread_mgr.close()


@celery_app.task(
    name="backend.tasks.scrape_tasks.cleanup_old_logs",
    queue="default",
)
def cleanup_old_logs() -> dict:
    """
    Periodic task: remove log entries older than the configured retention period.
    Scheduled via Celery Beat.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from backend.config import get_app_config
    from backend.database.connection import async_session_factory
    from backend.src.models.log_entry import LogEntry

    app_config = get_app_config()
    retention_days = app_config.log_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async def _cleanup():
        async with async_session_factory() as session:
            result = await session.execute(
                delete(LogEntry).where(LogEntry.created_at < cutoff)
            )
            await session.commit()
            return result.rowcount

    loop = asyncio.new_event_loop()
    try:
        deleted_count = loop.run_until_complete(_cleanup())
    finally:
        loop.close()

    task_logger.info(
        "Cleaned up %d log entries older than %d days",
        deleted_count,
        retention_days,
    )

    return {"deleted": deleted_count, "retention_days": retention_days}
