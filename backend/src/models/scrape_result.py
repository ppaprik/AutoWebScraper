#======================================================================================================
# A single result of a scrape job.
#======================================================================================================

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.models.base import Base, TimestampMixin
from backend.src.models.scrape_result_category import scrape_result_categories


class ScrapeResult(Base, TimestampMixin):
    """
    A single result of a scrape job.
    """

    __tablename__ = "scrape_results"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    content: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    page_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_length: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


    #---------------------------------------------------------------------------
    # Relationships — lazy="noload"
    job: Mapped["Job"] = relationship(
        "Job",
        back_populates="scrape_results",
        lazy="noload",
    )

    content_versions: Mapped[List["ContentVersion"]] = relationship(
        "ContentVersion",
        back_populates="scrape_result",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    categories: Mapped[List["Category"]] = relationship(
        "Category",
        secondary=scrape_result_categories,
        back_populates="scrape_results",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<ScrapeResult(id={self.id}, url='{self.url[:60]}')>"
