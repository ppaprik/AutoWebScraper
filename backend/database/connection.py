#======================================================================================================
# Creates the async SQLAlchemy engine and provides a session factory.
# Automatically recreates the engine when the event loop changes, which happens in Celery prefork workers that create a new loop per job.
#======================================================================================================

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import get_settings


def _build_engine() -> AsyncEngine:
    """Create a fresh async engine with connection pooling."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


class _SessionManager:
    """
    Manages the async engine and session factory lifecycle.
    Detects when the event loop has changed (e.g., in a Celery forked
    worker) and automatically creates a fresh engine bound to the
    current loop. This prevents the 'Future attached to a different
    loop' error.
    """

    def __init__(self) -> None:
        self._engine = None
        self._factory = None
        self._loop_id = None

    def _ensure_factory(self):
        """Create or recreate the engine and factory if the loop changed."""
        current_loop_id = None
        try:
            loop = asyncio.get_running_loop()
            current_loop_id = id(loop)
        except RuntimeError:
            pass

        if self._factory is None or self._loop_id != current_loop_id:
            # Engine is stale (different loop or first call) — build fresh
            self._engine = _build_engine()
            self._factory = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            self._loop_id = current_loop_id

        return self._factory

    def __call__(self):
        """
        Create a new AsyncSession.
        Drop-in replacement for async_sessionmaker() — all existing code
        that does 'async with async_session_factory() as session:' works
        unchanged.
        """
        return self._ensure_factory()()

    @property
    def engine(self):
        """Get the current engine (creating it if needed)."""
        self._ensure_factory()
        return self._engine

    async def dispose(self):
        """Cleanly shut down the connection pool."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._factory = None
            self._loop_id = None


#----------------------------------------------------------------------------------------------------
# Module-level singleton — all code imports this
_manager = _SessionManager()

# Drop-in compatible: async_session_factory() returns an AsyncSession
async_session_factory = _manager


async def get_session():
    """
    Dependency-injectable async session generator.
    Usage in FastAPI:
        @router.get("/example")
        async def example(session: AsyncSession = Depends(get_session)):
            ...
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


async def dispose_engine():
    """Cleanly shut down the connection pool (called on app shutdown)."""
    await _manager.dispose()
