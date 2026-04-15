#======================================================================================================
# Tests for DatabaseManager CRUD and content versioning logic.
#======================================================================================================

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.managers.database_manager import DatabaseManager
from backend.src.models import CrawlMode, JobStatus, LogLevel


@pytest.fixture
def db_manager() -> DatabaseManager:
    """Provide a fresh DatabaseManager instance."""
    return DatabaseManager()


#----------------------------------------------------------------------------------------------------
# JOB CRUD
class TestJobCRUD:

    @pytest.mark.asyncio
    async def test_create_job(self, db_session: AsyncSession, db_manager: DatabaseManager):
        """Creating a job returns a valid Job with PENDING status."""
        job = await db_manager.create_job(
            session=db_session,
            name="My Scrape",
            start_url="https://example.com",
            crawl_mode=CrawlMode.SINGLE,
            data_targets=["text"],
        )

        assert job is not None
        assert job.name == "My Scrape"
        assert job.start_url == "https://example.com"
        assert job.crawl_mode == CrawlMode.SINGLE
        assert job.status == JobStatus.PENDING
        assert job.pages_scraped == 0
        assert job.id is not None

    @pytest.mark.asyncio
    async def test_get_job(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job):
        """Getting a job by ID returns the correct job."""
        fetched = await db_manager.get_job(db_session, sample_job.id)
        assert fetched is not None
        assert fetched.id == sample_job.id
        assert fetched.name == sample_job.name

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, db_session: AsyncSession, db_manager: DatabaseManager):
        """Getting a non-existent job returns None."""
        result = await db_manager.get_job(db_session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_jobs(self, db_session: AsyncSession, db_manager: DatabaseManager):
        """Listing jobs returns all created jobs."""
        await db_manager.create_job(db_session, "Job 1", "https://a.com", CrawlMode.SINGLE)
        await db_manager.create_job(db_session, "Job 2", "https://b.com", CrawlMode.INFINITE)

        jobs = await db_manager.list_jobs(db_session)
        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_status(self, db_session: AsyncSession, db_manager: DatabaseManager):
        """Filtering jobs by status returns only matching jobs."""
        job1 = await db_manager.create_job(db_session, "Job 1", "https://a.com", CrawlMode.SINGLE)
        job2 = await db_manager.create_job(db_session, "Job 2", "https://b.com", CrawlMode.SINGLE)
        await db_manager.update_job_status(db_session, job1.id, JobStatus.RUNNING)

        running = await db_manager.list_jobs(db_session, status=JobStatus.RUNNING)
        assert len(running) == 1
        assert running[0].name == "Job 1"

    @pytest.mark.asyncio
    async def test_update_job_status(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job):
        """Updating job status changes the status field."""
        updated = await db_manager.update_job_status(
            db_session, sample_job.id, JobStatus.RUNNING
        )
        assert updated.status == JobStatus.RUNNING
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_update_job_progress(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job):
        """Updating job progress changes the counter fields."""
        await db_manager.update_job_progress(
            db_session, sample_job.id,
            pages_scraped=10,
            pages_failed=2,
            total_pages_discovered=50,
        )

        job = await db_manager.get_job(db_session, sample_job.id)
        assert job.pages_scraped == 10
        assert job.pages_failed == 2
        assert job.total_pages_discovered == 50

    @pytest.mark.asyncio
    async def test_delete_job(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job):
        """Deleting a job removes it from the database."""
        deleted = await db_manager.delete_job(db_session, sample_job.id)
        assert deleted is True

        fetched = await db_manager.get_job(db_session, sample_job.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_count_jobs(self, db_session: AsyncSession, db_manager: DatabaseManager):
        """Count jobs returns the correct total."""
        await db_manager.create_job(db_session, "J1", "https://a.com", CrawlMode.SINGLE)
        await db_manager.create_job(db_session, "J2", "https://b.com", CrawlMode.SINGLE)

        count = await db_manager.count_jobs(db_session)
        assert count == 2


#----------------------------------------------------------------------------------------------------
# CATEGORY CRUD
class TestCategoryCRUD:

    @pytest.mark.asyncio
    async def test_create_category(self, db_session: AsyncSession, db_manager: DatabaseManager):
        """Creating a category stores all fields correctly."""
        cat = await db_manager.create_category(
            session=db_session,
            name="Sports",
            description="Sports news",
            keywords=["football", "basketball"],
            url_patterns=[{"type": "contains", "pattern": "sport"}],
        )

        assert cat.name == "Sports"
        assert cat.keywords == ["football", "basketball"]
        assert cat.is_active is True

    @pytest.mark.asyncio
    async def test_update_category(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_category):
        """Updating a category changes the specified fields."""
        updated = await db_manager.update_category(
            db_session, sample_category.id,
            name="Tech & Science",
            is_active=False,
        )

        assert updated.name == "Tech & Science"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_delete_category(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_category):
        """Deleting a category removes it."""
        deleted = await db_manager.delete_category(db_session, sample_category.id)
        assert deleted is True

        fetched = await db_manager.get_category(db_session, sample_category.id)
        assert fetched is None


#----------------------------------------------------------------------------------------------------
# CREDENTIAL CRUD
class TestCredentialCRUD:

    @pytest.mark.asyncio
    async def test_create_credential(self, db_session: AsyncSession, db_manager: DatabaseManager):
        """Creating a credential stores the encrypted password."""
        cred = await db_manager.create_credential(
            session=db_session,
            domain="test.com",
            username="admin",
            encrypted_password="encrypted_data_here",
            login_url="https://test.com/login",
        )

        assert cred.domain == "test.com"
        assert cred.username == "admin"
        assert cred.encrypted_password == "encrypted_data_here"

    @pytest.mark.asyncio
    async def test_get_credential_by_domain(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_credential):
        """Looking up a credential by domain returns the correct one."""
        cred = await db_manager.get_credential_by_domain(db_session, "example.com")
        assert cred is not None
        assert cred.username == "testuser"


#----------------------------------------------------------------------------------------------------
# LOG ENTRIES
class TestLogEntries:

    @pytest.mark.asyncio
    async def test_create_log_entry(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job):
        """Creating a log entry stores it correctly."""
        entry = await db_manager.create_log_entry(
            session=db_session,
            job_id=sample_job.id,
            level=LogLevel.INFO,
            message="Started scraping",
            source_url="https://example.com",
            component="scraper",
        )

        assert entry.message == "Started scraping"
        assert entry.level == LogLevel.INFO
        assert entry.job_id == sample_job.id

    @pytest.mark.asyncio
    async def test_get_log_entries(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job):
        """Fetching log entries returns them in order."""
        await db_manager.create_log_entry(db_session, sample_job.id, LogLevel.INFO, "First")
        await db_manager.create_log_entry(db_session, sample_job.id, LogLevel.ERROR, "Second")

        entries = await db_manager.get_log_entries(db_session, sample_job.id)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_count_log_entries(self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job):
        """Counting log entries returns correct total."""
        await db_manager.create_log_entry(db_session, sample_job.id, LogLevel.INFO, "Msg1")
        await db_manager.create_log_entry(db_session, sample_job.id, LogLevel.INFO, "Msg2")
        await db_manager.create_log_entry(db_session, sample_job.id, LogLevel.ERROR, "Msg3")

        count = await db_manager.count_log_entries(db_session, sample_job.id)
        assert count == 3


#----------------------------------------------------------------------------------------------------
# CONTENT VERSIONING
class TestContentVersioning:

    @pytest.mark.asyncio
    async def test_store_scrape_result_creates_snapshot(
        self, db_session: AsyncSession, db_manager: DatabaseManager, sample_job,
    ):
        """First scrape of a URL creates a full content snapshot."""
        content = [
            {"type": "heading", "content": "Hello World"},
            {"type": "paragraph", "content": "Some text here."},
        ]

        result = await db_manager.store_scrape_result(
            session=db_session,
            job_id=sample_job.id,
            url="https://example.com/new-page",
            content=content,
            http_status=200,
            page_title="Hello Page",
        )

        assert result.url == "https://example.com/new-page"
        assert result.content_hash is not None
        assert result.content_length > 0

    @pytest.mark.asyncio
    async def test_content_hash_computation(self, db_manager: DatabaseManager):
        """Content hash is deterministic for identical content."""
        content_a = [{"type": "paragraph", "content": "Hello"}]
        content_b = [{"type": "paragraph", "content": "Hello"}]
        content_c = [{"type": "paragraph", "content": "Different"}]

        hash_a = db_manager._compute_content_hash(content_a)
        hash_b = db_manager._compute_content_hash(content_b)
        hash_c = db_manager._compute_content_hash(content_c)

        assert hash_a == hash_b
        assert hash_a != hash_c

    def test_compute_diff(self, db_manager: DatabaseManager):
        """Diff computation detects added, removed, and modified blocks."""
        old = [
            {"type": "heading", "content": "Title"},
            {"type": "paragraph", "content": "Old paragraph."},
            {"type": "paragraph", "content": "To be removed."},
        ]

        new = [
            {"type": "heading", "content": "Title"},
            {"type": "paragraph", "content": "New paragraph."},
            {"type": "code_block", "content": "print('new')"},
        ]

        diff = db_manager._compute_diff(old, new)

        assert "added" in diff
        assert "removed" in diff
        assert "modified" in diff

        # "To be removed" should be in removed
        removed_texts = [b.get("content", "") for b in diff["removed"]]
        assert "To be removed." in removed_texts

        # "print('new')" should be in added
        added_texts = [b.get("content", "") for b in diff["added"]]
        assert "print('new')" in added_texts

    def test_apply_diff(self, db_manager: DatabaseManager):
        """Applying a diff to old content produces the expected new content."""
        old = [
            {"type": "heading", "content": "Title"},
            {"type": "paragraph", "content": "Keep this."},
        ]

        diff = {
            "added": [{"type": "paragraph", "content": "New block."}],
            "removed": [],
            "modified": [],
        }

        result = db_manager._apply_diff(old, diff)
        contents = [b.get("content", "") for b in result]
        assert "Title" in contents
        assert "Keep this." in contents
        assert "New block." in contents
