from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.models.base import Base, TimestampMixin


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class CrawlMode(str, enum.Enum):
    SINGLE = "single"
    RULE_BASED = "rule_based"
    INFINITE = "infinite"
    CATEGORY = "category"


class JsMode(str, enum.Enum):
    """
    Controls whether Playwright is used for JavaScript rendering.
    AUTO   — aiohttp first; if JSDetector scores >= threshold, Playwright.
    ALWAYS — always Playwright.
    NEVER  — aiohttp only.
    """
    AUTO = "auto"
    ALWAYS = "always"
    NEVER = "never"


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_url: Mapped[str] = mapped_column(Text, nullable=False)

    crawl_mode: Mapped[CrawlMode] = mapped_column(
        Enum(
            CrawlMode,
            name="crawl_mode_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=CrawlMode.SINGLE,
    )

    js_mode: Mapped[JsMode] = mapped_column(
        Enum(
            JsMode,
            name="js_mode_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=JsMode.AUTO,
    )

    url_rules: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    data_targets: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    filter_category_ids: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True
    )
    credential_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status_enum",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=JobStatus.PENDING,
    )

    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    pages_scraped: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    pages_failed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    total_pages_discovered: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pages_per_second: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships — lazy="noload" 
    # DO NOT change to selectin/subquery/joined. See class docstring.
    scrape_results: Mapped[List["ScrapeResult"]] = relationship(
        "ScrapeResult",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    log_entries: Mapped[List["LogEntry"]] = relationship(
        "LogEntry",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<Job(id={self.id}, name='{self.name}', "
            f"status={self.status.value})>"
        )
