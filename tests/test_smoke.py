#======================================================================================================
# Smoke tests
#======================================================================================================

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class TestImportSmoke:
    """Verify all modules import without errors."""

    def test_import_config(self):
        from backend.config import get_settings, get_app_config
        settings = get_settings()
        assert settings is not None
        config = get_app_config()
        assert config is not None

    def test_import_models(self):
        from backend.src.models import (
            Base, Job, ScrapeResult, ContentVersion,
            Category, Credential, LogEntry,
        )
        assert Base is not None
        assert Job.__tablename__ == "jobs"
        assert ScrapeResult.__tablename__ == "scrape_results"

    def test_import_managers(self):
        from backend.src.managers import (
            DatabaseManager, SessionManager, ScraperManager,
            ThreadManager, CategoryClassifier,
        )
        assert DatabaseManager is not None
        assert ScraperManager is not None

    def test_import_services(self):
        from backend.src.services import (
            ContentExtractor, CodeBlockHandler, URLResolver,
            DiffEngine, ExportService, EncryptionService,
        )
        assert ContentExtractor is not None
        assert CodeBlockHandler is not None

    def test_import_api(self):
        from backend.api.router import api_router
        assert api_router is not None

    def test_import_schemas(self):
        from backend.api.schemas import (
            JobCreate, JobResponse, CategoryCreate,
            CredentialCreate, LogEntryResponse,
        )
        assert JobCreate is not None

    def test_import_tasks(self):
        from backend.tasks.celery_app import celery_app
        assert celery_app is not None

    def test_import_app(self):
        from WebScraper import app
        assert app is not None
        assert app.title == "WebScraper"


class TestConfigSmoke:
    """Verify configuration loads correctly."""

    def test_settings_has_database_url(self):
        from backend.config import get_settings
        settings = get_settings()
        assert "postgresql" in settings.database_url

    def test_settings_has_redis_url(self):
        from backend.config import get_settings
        settings = get_settings()
        assert "redis" in settings.redis_url

    def test_app_config_has_defaults(self):
        from backend.config import get_app_config
        config = get_app_config()
        assert config.max_pages_per_job > 0
        assert config.max_crawl_depth > 0
        assert config.min_text_density > 0


class TestDatabaseSmoke:
    """Verify database operations work with in-memory SQLite."""

    @pytest.mark.asyncio
    async def test_create_tables(self, async_engine):
        """All model tables are created successfully."""
        from sqlalchemy import inspect as sa_inspect

        async with async_engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: sa_inspect(sync_conn).get_table_names()
            )

        expected_tables = [
            "jobs", "scrape_results", "content_versions",
            "categories", "credentials", "log_entries",
        ]
        for table in expected_tables:
            assert table in table_names, f"Table '{table}' not found"

    @pytest.mark.asyncio
    async def test_crud_job_lifecycle(self, db_session: AsyncSession):
        """Full job lifecycle: create → update status → delete."""
        from backend.src.managers.database_manager import DatabaseManager
        from backend.src.models import CrawlMode, JobStatus

        db = DatabaseManager()

        # Create
        job = await db.create_job(
            db_session, "Smoke Test", "https://example.com", CrawlMode.SINGLE
        )
        assert job.id is not None
        assert job.status == JobStatus.PENDING

        # Update
        updated = await db.update_job_status(db_session, job.id, JobStatus.RUNNING)
        assert updated.status == JobStatus.RUNNING

        # Delete
        deleted = await db.delete_job(db_session, job.id)
        assert deleted is True


class TestExtractionSmoke:
    """Verify the extraction pipeline works end-to-end."""

    def test_extract_simple_page(self):
        """Extract content from a simple HTML page."""
        from backend.src.services.content_extractor import ContentExtractor

        html = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <article>
                <h1>Main Heading for the Test Article</h1>
                <p>This is a paragraph with enough words to pass all the 
                   content extraction filters and density heuristics that 
                   the extractor applies to determine if text is real content.</p>
                <pre><code class="language-python">
def example():
    return "This code should be preserved"
                </code></pre>
                <p>Another paragraph following the code block with sufficient 
                   length to be recognized as meaningful content by the pipeline.</p>
            </article>
        </body>
        </html>
        """

        extractor = ContentExtractor()
        blocks = extractor.extract(html, url="https://example.com/test")

        assert len(blocks) > 0

        # Should have at least one code block
        code_blocks = [b for b in blocks if b["type"] == "code_block"]
        assert len(code_blocks) >= 1
        assert "def example" in code_blocks[0]["content"]

        # Title extraction
        title = extractor.extract_title(html)
        assert title == "Test Page"

    def test_code_detection_without_tags(self):
        """Code is detected even without explicit code tags."""
        from backend.src.services.code_block_handler import CodeBlockHandler
        from bs4 import BeautifulSoup

        html = """
        <div class="highlight-python">
            <pre>
import os
import sys

def main():
    path = os.path.join("/tmp", "test")
    if os.path.exists(path):
        sys.exit(0)
    return None
            </pre>
        </div>
        """

        handler = CodeBlockHandler()
        soup = BeautifulSoup(html, "lxml")
        blocks = handler.extract_code_blocks(soup)

        assert len(blocks) >= 1
        assert blocks[0]["type"] == "code_block"
        assert "import os" in blocks[0]["content"]


class TestEncryptionSmoke:
    """Verify encryption service works."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting and decrypting returns the original value."""
        from backend.src.services.encryption_service import EncryptionService

        service = EncryptionService()
        original = "my_secret_password_123!"

        encrypted = service.encrypt(original)
        assert encrypted != original
        assert len(encrypted) > 0

        decrypted = service.decrypt(encrypted)
        assert decrypted == original

    def test_generate_key(self):
        """Key generation produces a valid Fernet key."""
        from backend.src.services.encryption_service import EncryptionService

        key = EncryptionService.generate_key()
        assert len(key) > 0
        assert isinstance(key, str)
