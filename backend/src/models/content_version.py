#======================================================================================================
# A single version of a URL's content
#======================================================================================================

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.models.base import Base, TimestampMixin


class ContentVersion(Base, TimestampMixin):
    __tablename__ = "content_versions"

    # --- Foreign keys ---
    scrape_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scrape_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Versioning ---
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # SHA-256 hash of this version's full content (for quick comparison).
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # True if this is the initial snapshot (full content stored).
    is_snapshot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Full content (only populated when is_snapshot=True).
    full_content: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Diff against previous version (only populated when is_snapshot=False).
    # Stored as a JSON object with keys: "added", "removed", "modified".
    diff_content: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Human-readable summary of changes.
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Number of content blocks that changed in this version.
    blocks_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- Relationships ---
    scrape_result: Mapped["ScrapeResult"] = relationship(
        "ScrapeResult",
        back_populates="content_versions",
    )

    def __repr__(self) -> str:
        kind = "snapshot" if self.is_snapshot else "diff"
        return f"<ContentVersion(id={self.id}, v{self.version_number}, {kind})>"
