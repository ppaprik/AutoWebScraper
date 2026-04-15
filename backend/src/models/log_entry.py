#======================================================================================================
# A single log line produced during job execution.
# Stored in the database and also broadcast over WebSocket for live display.
#======================================================================================================

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.src.models.base import Base, TimestampMixin


class LogLevel(str, enum.Enum):
    """Severity levels for log entries."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogEntry(Base, TimestampMixin):
    """
    A single log line produced during job execution.
    Stored in the database and also broadcast over WebSocket for live display.
    """

    __tablename__ = "log_entries"

    # --- Foreign keys ---
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Log data ---
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel, name="log_level_enum", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=LogLevel.INFO,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional: which URL was being processed when this log was emitted
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional: component that produced the log (e.g., "scraper", "extractor")
    component: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- Relationships ---
    job: Mapped["Job"] = relationship("Job", back_populates="log_entries")

    def __repr__(self) -> str:
        return f"<LogEntry(id={self.id}, level={self.level.value}, msg='{self.message[:40]}...')>"
