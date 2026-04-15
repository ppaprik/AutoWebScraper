#======================================================================================================
# Tests for the /api/scrape endpoints.
#======================================================================================================

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.src.models.base import Base
from backend.src.managers.database_manager import DatabaseManager


@pytest_asyncio.fixture
async def test_app():
    """Create a test FastAPI app with an in-memory database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

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
class TestScrapeAPI:

    async def test_get_results_job_not_found(self, test_app):
        """GET /api/scrape/{job_id}/results returns 404 for non-existent job."""
        transport = ASGITransport(app=test_app)
        fake_id = str(uuid.uuid4())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/scrape/{fake_id}/results")

        assert response.status_code == 404

    async def test_get_versions_no_results(self, test_app):
        """GET /api/scrape/versions returns 404 when no versions exist."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/scrape/versions",
                params={"url": "https://nonexistent.com/page"},
            )

        assert response.status_code == 404
