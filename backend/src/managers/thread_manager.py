#======================================================================================================
# Manages execution of async scraping jobs within synchronous Celery workers.
#======================================================================================================

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Dict, Optional

import redis as redis_sync

from backend.config import get_settings
from backend.logging_config import get_logger
from backend.src.managers.scraper_manager import ScraperManager

logger = get_logger("thread_manager")

_STOP_KEY_PREFIX  = "webscraper:job:stop:"
_PAUSE_KEY_PREFIX = "webscraper:job:pause:"

# Jobs in these states must never be re-executed
_TERMINAL_STATUSES = {"completed", "stopped", "failed", "paused"}


class ThreadManager:
    """
    Manages execution of async scraping jobs within synchronous Celery workers.
    Provides stop/pause signalling via Redis flags.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._redis = redis_sync.Redis(
            host=self._settings.redis_host,
            port=self._settings.redis_port,
            db=self._settings.redis_db,
            decode_responses=True,
        )

    def execute_job(
        self,
        job_id: uuid.UUID,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a scraping job synchronously (called from Celery task).

        Enforces run-once: reads DB status first. Terminal jobs exit instantly.
        """
        # Run-once guard
        guard_loop = asyncio.new_event_loop()
        try:
            current_status = guard_loop.run_until_complete(
                self._get_job_status(job_id)
            )
        finally:
            guard_loop.close()

        if current_status is not None and current_status in _TERMINAL_STATUSES:
            logger.info(
                "job_already_terminal",
                job_id=str(job_id),
                status=current_status,
            )
            return {
                "pages_scraped": 0,
                "pages_failed": 0,
                "total_discovered": 0,
                "status": current_status,
                "skipped": True,
            }

        #---------------------------------------------------------------------------
        # Clear any leftover signals from a previous run
        self._clear_signals(job_id)
        stop_checker = self._make_stop_checker(job_id)

        logger.info("executing_job", job_id=str(job_id), timeout=timeout)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                self._run_with_timeout(job_id, stop_checker, timeout)
            )
            return result
        except asyncio.CancelledError:
            logger.warning("job_cancelled", job_id=str(job_id))
            return {
                "pages_scraped": 0,
                "pages_failed": 0,
                "total_discovered": 0,
                "status": "stopped",
            }
        except Exception as exc:
            logger.error("job_execution_error", job_id=str(job_id), error=str(exc))
            return {
                "pages_scraped": 0,
                "pages_failed": 0,
                "total_discovered": 0,
                "status": "failed",
                "error": str(exc),
            }
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            finally:
                loop.close()
                self._clear_signals(job_id)

    async def _get_job_status(self, job_id: uuid.UUID) -> Optional[str]:
        """Read the job's current status from the database."""
        from backend.src.managers.database_manager import DatabaseManager
        from backend.database.connection import async_session_factory

        try:
            db = DatabaseManager()
            async with async_session_factory() as session:
                job = await db.get_job(session, job_id)
                return job.status.value if job else None
        except Exception as exc:
            logger.warning(
                "status_check_failed", job_id=str(job_id), error=str(exc)
            )
            return None

    async def _run_with_timeout(
        self,
        job_id: uuid.UUID,
        stop_checker: Callable[[], Optional[str]],
        timeout: Optional[int],
    ) -> Dict[str, Any]:
        """Run the scraper manager with an optional timeout."""
        scraper = ScraperManager()

        if timeout is not None:
            try:
                return await asyncio.wait_for(
                    scraper.run_job(job_id, stop_check=stop_checker),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "job_timed_out", job_id=str(job_id), timeout=timeout
                )
                return {
                    "pages_scraped": 0,
                    "pages_failed": 0,
                    "total_discovered": 0,
                    "status": "failed",
                    "error": f"Job timed out after {timeout} seconds",
                }
        else:
            return await scraper.run_job(job_id, stop_check=stop_checker)

    #---------------------------------------------------------------------------
    # CONTROL SIGNALS
    def send_stop_signal(self, job_id: Any) -> None:
        """Write the stop flag to Redis."""
        self._redis.setex(f"{_STOP_KEY_PREFIX}{job_id}", 3600, "1")
        logger.info("stop_signal_sent", job_id=str(job_id))

    def send_pause_signal(self, job_id: Any) -> None:
        """Write the pause flag to Redis."""
        self._redis.setex(f"{_PAUSE_KEY_PREFIX}{job_id}", 3600, "1")
        logger.info("pause_signal_sent", job_id=str(job_id))

    def send_resume_signal(self, job_id: Any) -> None:
        """Clear the pause flag so the job resumes."""
        self._redis.delete(f"{_PAUSE_KEY_PREFIX}{job_id}")
        logger.info("resume_signal_sent", job_id=str(job_id))

    def is_stop_requested(self, job_id: Any) -> bool:
        return self._redis.exists(f"{_STOP_KEY_PREFIX}{job_id}") > 0

    def is_pause_requested(self, job_id: Any) -> bool:
        return self._redis.exists(f"{_PAUSE_KEY_PREFIX}{job_id}") > 0

    def _clear_signals(self, job_id: Any) -> None:
        self._redis.delete(
            f"{_STOP_KEY_PREFIX}{job_id}",
            f"{_PAUSE_KEY_PREFIX}{job_id}",
        )

    def _make_stop_checker(self, job_id: Any) -> Callable[[], Optional[str]]:
        """
        Return a callable that ScraperManager polls between URL batches.
        Returns "stop", "pause", or None. Never blocks.
        """
        def check() -> Optional[str]:
            if self.is_stop_requested(job_id):
                logger.info("stop_detected", job_id=str(job_id))
                return "stop"
            if self.is_pause_requested(job_id):
                logger.info("job_paused_waiting", job_id=str(job_id))
                return "pause"
            return None

        return check

    def close(self) -> None:
        try:
            self._redis.close()
        except Exception:
            pass
