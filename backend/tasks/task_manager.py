#======================================================================================================
# High-level task management interface.
# Wraps Celery operations (dispatch, revoke, inspect) behind clean methods
# that the API endpoints call.
#======================================================================================================

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from backend.logging_config import get_logger
from backend.tasks.celery_app import celery_app

logger = get_logger("task_manager")


class TaskManager:
    """
    Provides a clean interface for managing Celery tasks from the API layer.
    Handles task dispatching, status inspection, revocation, and queue stats.
    """

    def dispatch_scrape_job(self, job_id: uuid.UUID) -> str:
        """
        Dispatch a scrape job to the Celery queue.
        Returns the Celery task ID.
        """
        from backend.tasks.scrape_tasks import execute_scrape_job

        task = execute_scrape_job.delay(str(job_id))
        logger.info("job_dispatched", job_id=str(job_id), task_id=task.id)
        return task.id

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get the current status of a Celery task.
        Returns a dict with state, result, and metadata.
        """
        result = celery_app.AsyncResult(task_id)

        status = {
            "task_id": task_id,
            "state": result.state,
            "result": None,
            "error": None,
        }

        if result.state == "SUCCESS":
            status["result"] = result.result
        elif result.state == "FAILURE":
            status["error"] = str(result.result)
        elif result.state == "PENDING":
            status["result"] = "Task is waiting in queue"

        return status

    def revoke_task(
        self,
        task_id: str,
        terminate: bool = True,
    ) -> bool:
        """
        Revoke (cancel) a Celery task.
        If terminate=True, sends SIGTERM to the worker process.
        """
        try:
            celery_app.control.revoke(
                task_id,
                terminate=terminate,
                signal="SIGTERM",
            )
            logger.info("task_revoked", task_id=task_id, terminate=terminate)
            return True
        except Exception as exc:
            logger.error("task_revoke_failed", task_id=task_id, error=str(exc))
            return False

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """
        Get a list of currently executing tasks across all workers.
        """
        inspect = celery_app.control.inspect()
        active = inspect.active()

        tasks = []
        if active:
            for worker_name, worker_tasks in active.items():
                for task_info in worker_tasks:
                    tasks.append({
                        "worker": worker_name,
                        "task_id": task_info.get("id"),
                        "task_name": task_info.get("name"),
                        "args": task_info.get("args"),
                        "started": task_info.get("time_start"),
                    })

        return tasks

    def get_queued_tasks(self) -> List[Dict[str, Any]]:
        """
        Get a list of tasks waiting in the queue (reserved but not started).
        """
        inspect = celery_app.control.inspect()
        reserved = inspect.reserved()

        tasks = []
        if reserved:
            for worker_name, worker_tasks in reserved.items():
                for task_info in worker_tasks:
                    tasks.append({
                        "worker": worker_name,
                        "task_id": task_info.get("id"),
                        "task_name": task_info.get("name"),
                        "args": task_info.get("args"),
                    })

        return tasks

    def get_worker_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the Celery worker pool.
        """
        inspect = celery_app.control.inspect()

        stats = {
            "workers": {},
            "total_active": 0,
            "total_reserved": 0,
        }

        # Worker status
        ping_result = inspect.ping()
        if ping_result:
            for worker_name in ping_result:
                stats["workers"][worker_name] = {"status": "online"}

        # Active task count per worker
        active = inspect.active()
        if active:
            for worker_name, tasks in active.items():
                if worker_name in stats["workers"]:
                    stats["workers"][worker_name]["active_tasks"] = len(tasks)
                stats["total_active"] += len(tasks)

        # Reserved (queued) task count per worker
        reserved = inspect.reserved()
        if reserved:
            for worker_name, tasks in reserved.items():
                if worker_name in stats["workers"]:
                    stats["workers"][worker_name]["reserved_tasks"] = len(tasks)
                stats["total_reserved"] += len(tasks)

        return stats

    def purge_queue(self, queue_name: str = "scrape") -> int:
        """
        Remove all pending tasks from a queue.
        Returns the number of purged messages.
        """
        try:
            purged = celery_app.control.purge()
            logger.info("queue_purged", queue=queue_name, count=purged)
            return purged
        except Exception as exc:
            logger.error("queue_purge_failed", queue=queue_name, error=str(exc))
            return 0
