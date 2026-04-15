#======================================================================================================
# Shared fixtures for pytest
#======================================================================================================

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.src.models.base import Base
from backend.src.models import (
    Category,
    ContentVersion,
    Credential,
    CrawlMode,
    Job,
    JobStatus,
    LogEntry,
    LogLevel,
    ScrapeResult,
)


#----------------------------------------------------------------------------------------------------
# Override env vars before any config import
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "0")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleV9mb3JfdGVzdGluZ19vbmx5XzEyMzQ1Njc4")

# Generate a valid Fernet key for tests
from cryptography.fernet import Fernet
_test_key = Fernet.generate_key().decode()
os.environ["ENCRYPTION_KEY"] = _test_key


#----------------------------------------------------------------------------------------------------
# Event loop fixture
@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


#----------------------------------------------------------------------------------------------------
# Database engine and session (in-memory SQLite)
@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session that rolls back after each test."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


#----------------------------------------------------------------------------------------------------
# Pre-populated test data
@pytest_asyncio.fixture
async def sample_job(db_session: AsyncSession) -> Job:
    """Create a sample job for testing."""
    job = Job(
        name="Test Job",
        start_url="https://example.com",
        crawl_mode=CrawlMode.SINGLE,
        status=JobStatus.PENDING,
        data_targets=["text"],
    )
    db_session.add(job)
    await db_session.flush()
    return job


@pytest_asyncio.fixture
async def sample_category(db_session: AsyncSession) -> Category:
    """Create a sample category for testing."""
    category = Category(
        name="Technology",
        description="Tech-related content",
        keywords=["software", "programming", "developer", "API"],
        url_patterns=[
            {"type": "contains", "pattern": "tech"},
            {"type": "domain", "pattern": "dev.to"},
        ],
        is_active=True,
    )
    db_session.add(category)
    await db_session.flush()
    return category


@pytest_asyncio.fixture
async def sample_credential(db_session: AsyncSession) -> Credential:
    """Create a sample credential for testing."""
    from backend.src.services.encryption_service import EncryptionService

    encryption = EncryptionService()
    encrypted_pw = encryption.encrypt("test_password_123")

    credential = Credential(
        domain="example.com",
        username="testuser",
        encrypted_password=encrypted_pw,
        login_url="https://example.com/login",
        username_selector='input[name="email"]',
        password_selector='input[name="password"]',
        submit_selector='button[type="submit"]',
    )
    db_session.add(credential)
    await db_session.flush()
    return credential


@pytest_asyncio.fixture
async def sample_scrape_result(db_session: AsyncSession, sample_job: Job) -> ScrapeResult:
    """Create a sample scrape result with content."""
    result = ScrapeResult(
        job_id=sample_job.id,
        url="https://example.com/page1",
        http_status=200,
        content=[
            {"type": "heading", "content": "Test Heading"},
            {"type": "paragraph", "content": "This is test paragraph content."},
            {"type": "code_block", "language": "python", "content": "print('hello')"},
        ],
        content_hash="abc123",
        page_title="Test Page",
        content_length=150,
    )
    db_session.add(result)
    await db_session.flush()
    return result
