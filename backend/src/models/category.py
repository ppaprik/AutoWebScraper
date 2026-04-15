#======================================================================================================
# A named category with associated keywords and URL patterns
#======================================================================================================

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.models.base import Base, TimestampMixin
from backend.src.models.scrape_result_category import scrape_result_categories


class Category(Base, TimestampMixin):
    """
    A named category with associated keywords and URL patterns
    """

    __tablename__ = "categories"

    # Display name
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Optional human-readable description.
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Keyword list for rule-based matching. Example: ["software", "programming", "developer", "API"]
    keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # URL patterns that belong to this category. Example: [{"type": "contains", "pattern": "tech"}]
    url_patterns: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Whether this category is active (soft-disable without deleting).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Back-reference to all scrape results assigned to this category.
    scrape_results: Mapped[List["ScrapeResult"]] = relationship(
        "ScrapeResult",
        secondary=scrape_result_categories,
        back_populates="categories",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name='{self.name}')>"
