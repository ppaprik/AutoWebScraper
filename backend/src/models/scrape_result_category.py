#======================================================================================================
# Association table for many-to-many relationship between ScrapeResult and Category.
#======================================================================================================

from __future__ import annotations

from sqlalchemy import ForeignKey, Table, Column
from sqlalchemy.dialects.postgresql import UUID

from backend.src.models.base import Base


scrape_result_categories = Table(
    "scrape_result_categories",
    Base.metadata,

    Column(
        "scrape_result_id",
        UUID(as_uuid=True),
        ForeignKey("scrape_results.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),

    Column(
        "category_id",
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        primary_key=True,
        nullable=False,
    ),
)
