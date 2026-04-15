#======================================================================================================
# Two config objects:
#   Settings        loads secrets and infrastructure URLs from .env
#   AppConfig       loads non-secret tuning parameters from .config
#
# Both are cached singletons via @lru_cache so they're only parsed once.
#======================================================================================================

from __future__ import annotations

import configparser
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


CONFIG_FILE_PATH = Path("/WebScraper/.config")


class Settings(BaseSettings):
    """Loads all secrets and connection strings from environment variables."""

    # Database
    postgres_user: str = "webscraper"
    postgres_password: str = ""
    postgres_db: str = "webscraper"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # Encryption
    encryption_key: str = ""

    # FastAPI
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_log_level: str = "info"

    # Celery
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    celery_worker_concurrency: int = 4

    # Scraper
    scraper_default_timeout: int = 30
    scraper_max_retries: int = 3
    scraper_retry_delay: float = 2.0
    scraper_user_agent: str = (
        "Mozilla/5.0 (compatible; WebScraper/1.0; +https://github.com/webscraper)"
    )
    scraper_max_concurrent_requests: int = 10
    scraper_respect_robots_txt: bool = True
    scraper_default_delay_between_requests: float = 1.0

    @property
    def database_url(self) -> str:
        """Async connection string for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Synchronous connection string used by Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Redis connection string."""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class AppConfig:
    """
    Reads the INI-style .config file for non-secret application settings.
    """

    def __init__(self, config_path: Path = CONFIG_FILE_PATH) -> None:
        self._parser = configparser.RawConfigParser()
        if config_path.exists():
            self._parser.read(config_path)


    #---------------------------------------------------------------------------
    # Scraper section
    @property
    def max_pages_per_job(self) -> int:
        return self._parser.getint("scraper", "max_pages_per_job", fallback=10000)

    @property
    def max_crawl_depth(self) -> int:
        return self._parser.getint("scraper", "max_crawl_depth", fallback=50)

    @property
    def js_detection_threshold(self) -> float:
        """
        Score threshold for auto JS detection.
        Pages scoring >= this value trigger Playwright rendering.
        Default 3.0. Lower = more aggressive (more Playwright calls).
        Higher = more conservative (only obvious SPAs get Playwright).
        """
        return self._parser.getfloat(
            "scraper", "js_detection_threshold", fallback=5.0
        )

    @property
    def concurrent_pages_per_job(self) -> int:
        """
        How many pages to scrape concurrently within a single job.
        Each concurrent slot is an asyncio coroutine making an independent
        HTTP request. Since HTTP is I/O-bound, this gives true parallelism
        without the GIL being a bottleneck.
        Default: 10. Raise to 20-50 on fast connections; lower on slow ones.
        """
        return self._parser.getint("scraper", "concurrent_pages_per_job", fallback=10)

    @property
    def blocked_domains(self) -> List[str]:
        raw = self._parser.get("scraper", "blocked_domains", fallback="")
        return [d.strip() for d in raw.split(",") if d.strip()]

    @property
    def skip_extensions(self) -> List[str]:
        raw = self._parser.get("scraper", "skip_extensions", fallback="")
        return [e.strip() for e in raw.split(",") if e.strip()]


    #---------------------------------------------------------------------------
    # Extraction section
    @property
    def min_text_density(self) -> float:
        return self._parser.getfloat("extraction", "min_text_density", fallback=0.25)

    @property
    def min_block_words(self) -> int:
        return self._parser.getint("extraction", "min_block_words", fallback=20)

    @property
    def strip_tags(self) -> List[str]:
        raw = self._parser.get(
            "extraction", "strip_tags",
            fallback="nav, footer, header, aside, script, style, noscript, iframe",
        )
        return [t.strip() for t in raw.split(",") if t.strip()]

    @property
    def strip_classes(self) -> List[str]:
        raw = self._parser.get(
            "extraction", "strip_classes",
            fallback="sidebar, advertisement, ad-container, social-share, cookie-banner, popup",
        )
        return [c.strip() for c in raw.split(",") if c.strip()]


    #----------------------------------------------------------------------------------------------------
    # Code detection section
    @property
    def min_symbol_density(self) -> float:
        return self._parser.getfloat("code_detection", "min_symbol_density", fallback=0.08)

    @property
    def code_symbols(self) -> List[str]:
        raw = self._parser.get(
            "code_detection", "code_symbols",
            fallback="{ } [ ] ; = => // /* */ ( ) < > :: -> | & % #",
        )
        return raw.split()


    #----------------------------------------------------------------------------------------------------
    # Categories section
    @property
    def default_categories(self) -> dict[str, List[str]]:
        """Returns a dict mapping category name to its keyword list."""
        categories: dict[str, List[str]] = {}
        if self._parser.has_section("categories"):
            for name, keywords_raw in self._parser.items("categories"):
                categories[name] = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        return categories


    #----------------------------------------------------------------------------------------------------
    # Classification section
    @property
    def classification_provider(self) -> str:
        return self._parser.get("classification", "provider", fallback="none").strip().lower()

    @property
    def classification_confidence_threshold(self) -> float:
        return self._parser.getfloat("classification", "confidence_threshold", fallback=0.4)

    @property
    def classification_max_words(self) -> int:
        return self._parser.getint("classification", "max_words", fallback=500)

    @property
    def classification_candidate_labels(self) -> List[str]:
        default = (
            "Food,History,Sport,Technology,Space,Science,Politics,"
            "Business,Health,Entertainment,Travel,Nature,Art,"
            "Education,Music,Film,Literature,Religion,Philosophy,"
            "Gaming,News,Finance,Fashion,Automotive,Pets"
        )
        raw = self._parser.get("classification", "candidate_labels", fallback=default)
        return [label.strip() for label in raw.split(",") if label.strip()]

    @property
    def classification_run_in_subprocess(self) -> bool:
        """
        If True, BART/classifier runs inside each worker subprocess.
        True  = full parallelism, N × 1.6 GB RAM (one model per process)
        False = classifier runs in coordinator, 1 × 1.6 GB RAM (sequential)
        """
        return self._parser.getboolean(
            "classification", "run_in_subprocess", fallback=True
        )

    @property
    def classification_config_dict(self) -> dict:
        """Full [classification] section as a plain dict for the provider factory."""
        if self._parser.has_section("classification"):
            return dict(self._parser.items("classification"))
        return {}


    #----------------------------------------------------------------------------------------------------
    # Logging section
    @property
    def log_retention_days(self) -> int:
        return self._parser.getint("logging", "log_retention_days", fallback=30)

    @property
    def max_log_entries_per_job(self) -> int:
        return self._parser.getint("logging", "max_log_entries_per_job", fallback=50000)


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton for environment-based settings."""
    return Settings()


@lru_cache()
def get_app_config() -> AppConfig:
    """Cached singleton for file-based application config."""
    return AppConfig()
