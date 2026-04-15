#======================================================================================================
# Pydantic models for API request validation and response serialization.
#======================================================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.src.models.job import CrawlMode, JobStatus, JsMode, JsMode
from backend.src.models.log_entry import LogLevel


#----------------------------------------------------------------------------------------------------
# JOBS
class URLRule(BaseModel):
    """A single URL filtering rule."""
    type: str = Field(..., description="Rule type: contains, starts_with, ends_with, regex, domain")
    pattern: str = Field(..., description="Pattern to match against")


class JobCreate(BaseModel):
    """Request body for creating a new scraping job."""
    name: str = Field(..., min_length=1, max_length=255)
    start_url: str = Field(..., min_length=1)
    crawl_mode: CrawlMode = Field(default=CrawlMode.SINGLE)
    url_rules: Optional[List[URLRule]] = None
    data_targets: Optional[List[str]] = Field(default=["text"])

    # Category used by CATEGORY crawl mode — determines which URL patterns to follow.
    category_id: Optional[uuid.UUID] = None

    # Multi-category content filter (OR logic).
    # If set, only pages classified into ANY of these categories are saved.
    # Empty list / None means classify everything and save it all.
    filter_category_ids: Optional[List[uuid.UUID]] = None

    credential_id: Optional[uuid.UUID] = None
    # JavaScript rendering mode: auto | always | never
    js_mode: JsMode = Field(default=JsMode.AUTO)


class JobResponse(BaseModel):
    """Response model for a single job."""
    id: uuid.UUID
    name: str
    start_url: str
    crawl_mode: CrawlMode
    url_rules: Optional[List[Dict[str, Any]]] = None
    data_targets: Optional[List[str]] = None
    category_id: Optional[uuid.UUID] = None
    filter_category_ids: Optional[List[Any]] = None
    credential_id: Optional[uuid.UUID] = None
    js_mode: JsMode = JsMode.AUTO
    status: JobStatus
    celery_task_id: Optional[str] = None
    pages_scraped: int = 0
    pages_failed: int = 0
    total_pages_discovered: int = 0
    pages_per_second: float = 0.0
    last_error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """Response model for listing jobs."""
    jobs: List[JobResponse]
    total: int


class JobActionRequest(BaseModel):
    """Request body for job control actions (pause/resume/stop)."""
    action: str = Field(..., description="One of: pause, resume, stop")


#----------------------------------------------------------------------------------------------------
# SCRAPE RESULTS
class ScrapeResultResponse(BaseModel):
    """Response model for a single scrape result."""
    id: uuid.UUID
    job_id: uuid.UUID
    url: str
    http_status: Optional[int] = None
    content: Optional[Any] = None
    content_hash: Optional[str] = None
    page_title: Optional[str] = None
    content_length: int = 0
    error: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ScrapeResultListResponse(BaseModel):
    """Response model for listing scrape results."""
    results: List[ScrapeResultResponse]
    total: int


#----------------------------------------------------------------------------------------------------
# CONTENT VERSIONS
class ContentVersionResponse(BaseModel):
    """Response model for a content version."""
    id: uuid.UUID
    scrape_result_id: uuid.UUID
    version_number: int
    content_hash: str
    is_snapshot: bool
    full_content: Optional[Any] = None
    diff_content: Optional[Any] = None
    change_summary: Optional[str] = None
    blocks_changed: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


#----------------------------------------------------------------------------------------------------
# CATEGORIES
class CategoryCreate(BaseModel):
    """Request body for creating a category."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    url_patterns: Optional[List[URLRule]] = None


class CategoryUpdate(BaseModel):
    """Request body for updating a category."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    keywords: Optional[List[str]] = None
    url_patterns: Optional[List[URLRule]] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    """Response model for a category."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    keywords: Optional[List[Any]] = None
    url_patterns: Optional[List[Any]] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CategoryListResponse(BaseModel):
    """Response model for listing categories."""
    categories: List[CategoryResponse]


#----------------------------------------------------------------------------------------------------
# CREDENTIALS
class CredentialCreate(BaseModel):
    """Request body for creating a credential."""
    domain: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, description="Plaintext password — encrypted at rest")
    login_url: Optional[str] = None
    username_selector: Optional[str] = None
    password_selector: Optional[str] = None
    submit_selector: Optional[str] = None


class CredentialUpdate(BaseModel):
    """Request body for updating a credential."""
    domain: Optional[str] = Field(None, max_length=255)
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, description="New plaintext password — will be re-encrypted")
    login_url: Optional[str] = None
    username_selector: Optional[str] = None
    password_selector: Optional[str] = None
    submit_selector: Optional[str] = None


class CredentialResponse(BaseModel):
    """Response model for a credential (password is NEVER returned)."""
    id: uuid.UUID
    domain: str
    username: str
    login_url: Optional[str] = None
    username_selector: Optional[str] = None
    password_selector: Optional[str] = None
    submit_selector: Optional[str] = None
    has_password: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CredentialListResponse(BaseModel):
    """Response model for listing credentials."""
    credentials: List[CredentialResponse]


#----------------------------------------------------------------------------------------------------
# LOG ENTRIES
class LogEntryResponse(BaseModel):
    """Response model for a log entry."""
    id: uuid.UUID
    job_id: uuid.UUID
    level: LogLevel
    message: str
    source_url: Optional[str] = None
    component: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LogEntryListResponse(BaseModel):
    """Response model for listing log entries."""
    entries: List[LogEntryResponse]
    total: int


#----------------------------------------------------------------------------------------------------
# ANALYTICS
class AnalyticsStatsResponse(BaseModel):
    """Overall scraping statistics."""
    total_jobs: int
    total_pages_scraped: int
    total_content_versions: int
    total_errors: int
    total_content_bytes: int


class AnalyticsVolumeEntry(BaseModel):
    """A single data point in scrape volume over time."""
    day: str
    count: int


class AnalyticsCategoryEntry(BaseModel):
    """Job count per category."""
    category: str
    job_count: int


#----------------------------------------------------------------------------------------------------
# GENERIC
class MessageResponse(BaseModel):
    """Generic success/error message."""
    message: str
    success: bool = True
