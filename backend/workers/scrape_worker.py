#======================================================================================================
# Handles worker lifecycle signals: init, ready, shutdown, task pre/post run,
# and task failure. Triggers classification model warmup on startup so the
# provider is ready before the first scrape task arrives.
#======================================================================================================

from __future__ import annotations

import asyncio
import os
from typing import Any

from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    worker_init,
    worker_ready,
    worker_shutdown,
)

from backend.logging_config import get_logger, setup_logging

logger = get_logger("scrape_worker")


#----------------------------------------------------------------------------------------------------
# Classification model warmup
def _run_warmup() -> None:
    """
    Initialize and warm up the classification provider synchronously.

    No asyncio event loop exists at worker_init time, so we spin up a
    temporary one just for this warmup call.

    For BART: downloads the model on first run (~1.6 GB to model_cache
    volume) then loads it. Subsequent starts load from the volume cache
    in 5-15 seconds.

    For NullProvider / HttpApiProvider: effectively instant.

    Errors are logged but never crash the worker — a broken classifier
    must not prevent scraping. Pages will be tagged as Uncategorized.
    """
    try:
        from backend.src.services.classification_service import warmup_classification_service

        loop = asyncio.new_event_loop()

        try:
            loop.run_until_complete(warmup_classification_service())
        finally:
            loop.close()

    except Exception as exc:
        logger.warning("classifier_warmup_failed", error=str(exc))



#----------------------------------------------------------------------------------------------------
# Worker lifecycle signals
@worker_init.connect
def on_worker_init(**kwargs: Any) -> None:
    """Called when the worker process starts, before accepting tasks."""
    setup_logging("INFO")
    logger.info("worker_initializing")
    _run_warmup()


@worker_ready.connect
def on_worker_ready(**kwargs: Any) -> None:
    """Called when the worker is ready to accept tasks."""
    logger.info("worker_ready", pid=os.getpid())


@worker_shutdown.connect
def on_worker_shutdown(**kwargs: Any) -> None:
    """Called when the worker is shutting down."""
    logger.info("worker_shutting_down")



#----------------------------------------------------------------------------------------------------
# Task lifecycle signals
@task_prerun.connect
def on_task_prerun(
    task_id: str,
    task: Any,
    args: Any,
    **kwargs: Any,
) -> None:
    """Called just before a task starts executing."""
    job_id: str = args[0] if args else "unknown"
    logger.info("task_starting", task_id=task_id, task_name=task.name, job_id=job_id)


@task_postrun.connect
def on_task_postrun(
    task_id: str,
    task: Any,
    args: Any,
    retval: Any,
    state: str,
    **kwargs: Any,
) -> None:
    """Called after a task finishes executing."""
    job_id: str = args[0] if args else "unknown"
    logger.info(
        "task_completed",
        task_id=task_id,
        task_name=task.name,
        job_id=job_id,
        state=state,
    )


@task_failure.connect
def on_task_failure(
    task_id: str,
    exception: Exception,
    args: Any,
    **kwargs: Any,
) -> None:
    """Called when a task raises an unhandled exception."""
    job_id: str = args[0] if args else "unknown"
    logger.error("task_failed", task_id=task_id, job_id=job_id, error=str(exception))
