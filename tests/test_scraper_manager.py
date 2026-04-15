#======================================================================================================
# Tests for the ScraperManager
#======================================================================================================

from __future__ import annotations

import pytest

from backend.src.managers.scraper_manager import ScraperManager


class TestScraperManager:

    def test_instantiation(self):
        """ScraperManager can be instantiated without errors."""
        mgr = ScraperManager()
        assert mgr is not None

    def test_has_content_extractor(self):
        """ScraperManager has a content extractor."""
        mgr = ScraperManager()
        assert mgr._content_extractor is not None

    def test_has_url_resolver(self):
        """ScraperManager has a URL resolver."""
        mgr = ScraperManager()
        assert mgr._url_resolver is not None

    def test_has_session_manager(self):
        """ScraperManager has a session manager."""
        mgr = ScraperManager()
        assert mgr._session_manager is not None

    def test_has_db_manager(self):
        """ScraperManager has a database manager."""
        mgr = ScraperManager()
        assert mgr._db_manager is not None

    def test_semaphore_configured(self):
        """Concurrency semaphore is configured from settings."""
        mgr = ScraperManager()
        assert mgr._semaphore is not None

    def test_request_delay_configured(self):
        """Request delay is loaded from settings."""
        mgr = ScraperManager()
        assert mgr._request_delay >= 0
