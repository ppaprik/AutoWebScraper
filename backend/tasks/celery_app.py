#======================================================================================================
# Celery application instance and configuration.
# Used by the worker, beat scheduler, and API to dispatch/manage tasks.
#======================================================================================================

from __future__ import annotations

from celery import Celery

from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "webscraper",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


#----------------------------------------------------------------------------------------------------
# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Result expiry (24 hours)
    result_expires=86400,

    # Task routes — all tasks go to the default queue for simplicity
    task_default_queue="default",

    # Worker pool (prefork for multiprocessing)
    worker_pool="prefork",

    # Broker connection retry on startup (silence deprecation warning)
    broker_connection_retry_on_startup=True,

    # Periodic tasks (Celery Beat schedule)
    beat_schedule={
        # Example: clean up old log entries daily
        # "cleanup-old-logs": {
        #     "task": "backend.tasks.scrape_tasks.cleanup_old_logs",
        #     "schedule": 86400,  # every 24 hours
        # },
    },
)

# Explicitly import tasks so they get registered with Celery
import backend.tasks.scrape_tasks  # noqa: F401, E402
