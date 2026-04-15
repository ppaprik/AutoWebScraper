from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import get_settings
from backend.database.connection import async_session_factory, dispose_engine
from backend.logging_config import setup_logging, get_logger


FRONTEND_DIR = Path(__file__).parent / "frontend"
logger = get_logger("webscraper")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Startup and shutdown lifecycle manager.

    On startup:
      - Configure structured logging
      - Ensure the 'Uncategorized' protected category exists in the database.
        This is the fallback category assigned to pages that the AI classifier
        cannot confidently categorise. It must exist before any scrape job runs.

    On shutdown:
      - Close the async database connection pool cleanly.
    """
    settings = get_settings()
    setup_logging(settings.api_log_level)
    logger.info("webscraper_starting", host=settings.api_host, port=settings.api_port)

    # Guarantee the Uncategorized system category exists.
    # Uses a separate session so it doesn't interfere with the request lifecycle.
    try:
        from backend.src.managers.database_manager import DatabaseManager
        db_manager = DatabaseManager()
        async with async_session_factory() as session:
            await db_manager.ensure_uncategorized_exists(session)
            await session.commit()
        logger.info("uncategorized_category_ready")
    except Exception as exc:
        # Log but do not crash. The app can still serve requests without it.
        # The category will be created on the first classification attempt.
        logger.warning("uncategorized_category_setup_failed", error=str(exc))

    yield

    logger.info("webscraper_shutting_down")
    await dispose_engine()


#----------------------------------------------------------------------------------------------------
# Create the FastAPI application
app = FastAPI(
    title="WebScraper",
    description="Scalable async web scraping system with content versioning",
    version="1.0.0",
    lifespan=lifespan,
)


#----------------------------------------------------------------------------------------------------
# Register API routes (imported here to avoid circular imports)
from backend.api.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api")


#----------------------------------------------------------------------------------------------------
# Serve the static frontend
if FRONTEND_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="static",
    )

    @app.get("/")
    async def serve_frontend() -> FileResponse:
        """Serve the main frontend HTML page."""
        return FileResponse(str(FRONTEND_DIR / "index.html"))
