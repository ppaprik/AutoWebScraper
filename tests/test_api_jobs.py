#======================================================================================================
# Tests for the /api/jobs endpoints.
# Uses an in-memory SQLite database via dependency overrides.
#======================================================================================================

from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.src.models.base import Base
from backend.src.managers.database_manager import DatabaseManager


@pytest_asyncio.fixture
async def test_app():
    """Create a test FastAPI app with an in-memory database."""
    # Create in-memory engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    # Import app and override dependencies
    from WebScraper import app
    from backend.api.dependencies import get_db_session, get_database_manager

    async def override_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_db_manager():
        return DatabaseManager()

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_database_manager] = override_db_manager

    yield app

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
class TestJobsAPI:

    async def test_list_jobs_empty(self, test_app):
        """GET /api/jobs returns empty list when no jobs exist."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/jobs")

        assert response.status_code == 200
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0

    async def test_create_job(self, test_app):
        """POST /api/jobs creates a job and returns it."""
        transport = ASGITransport(app=test_app)

        # Mock Celery task dispatch to avoid needing a broker
        with patch("backend.api.endpoints.jobs.execute_scrape_job") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "mock-task-id-123"
            mock_task.delay.return_value = mock_result

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/jobs", json={
                    "name": "Test Job",
                    "start_url": "https://example.com",
                    "crawl_mode": "single",
                    "data_targets": ["text"],
                })

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Job"
        assert data["start_url"] == "https://example.com"
        assert data["crawl_mode"] == "single"
        assert data["status"] == "pending"

    async def test_create_job_validation_error(self, test_app):
        """POST /api/jobs with missing name returns 422."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/jobs", json={
                "start_url": "https://example.com",
            })

        assert response.status_code == 422

    async def test_get_job_not_found(self, test_app):
        """GET /api/jobs/{id} returns 404 for non-existent job."""
        transport = ASGITransport(app=test_app)
        fake_id = str(uuid.uuid4())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/jobs/{fake_id}")

        assert response.status_code == 404
