#======================================================================================================
# FastAPI dependency injection helpers.
# Provides database sessions and manager instances to endpoint functions.
#======================================================================================================

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.connection import async_session_factory
from backend.src.managers.database_manager import DatabaseManager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an async database session for a single request.
    Commits on success, rolls back on exception, always closes.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_database_manager() -> DatabaseManager:
    """
    Returns a DatabaseManager instance.
    The manager is stateless so a new instance per request is fine.
    """
    return DatabaseManager()
