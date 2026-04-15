#======================================================================================================
# Health check endpoint
#======================================================================================================

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from backend.database.connection import async_session_factory

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """
    Returns the health status of the application and its dependencies.
    Checks database connectivity by executing a simple query.
    """
    status = {
        "status": "healthy",
        "service": "webscraper",
        "database": "unknown",
        "redis": "unknown",
    }

    # Check PostgreSQL
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        status["database"] = "connected"
    except Exception as exc:
        status["database"] = f"error: {str(exc)[:100]}"
        status["status"] = "degraded"

    # Check Redis
    try:
        import redis as redis_lib
        from backend.config import get_settings
        settings = get_settings()
        r = redis_lib.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            socket_timeout=3,
        )
        r.ping()
        r.close()
        status["redis"] = "connected"
    except Exception as exc:
        status["redis"] = f"error: {str(exc)[:100]}"
        status["status"] = "degraded"

    return status
