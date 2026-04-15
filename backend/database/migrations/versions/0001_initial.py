#======================================================================================================
# Initial schema — create all tables

# Revision ID:      0001_initial
# Revision:         0001
# Create Date:      2025-01-15 00:00:00.000000
#======================================================================================================

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Jobs
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("start_url", sa.Text, nullable=False),
        sa.Column("crawl_mode", sa.Enum("single", "rule_based", "infinite", "category", name="crawl_mode_enum"), nullable=False),
        sa.Column("url_rules", JSONB, nullable=True),
        sa.Column("data_targets", JSONB, nullable=True),
        sa.Column("category_id", UUID(as_uuid=True), nullable=True),
        sa.Column("credential_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Enum("pending", "running", "paused", "completed", "failed", "stopped", name="job_status_enum"), nullable=False),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("pages_scraped", sa.Integer, default=0, nullable=False),
        sa.Column("pages_failed", sa.Integer, default=0, nullable=False),
        sa.Column("total_pages_discovered", sa.Integer, default=0, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_per_second", sa.Float, default=0.0, nullable=False),
        sa.Column("last_error", sa.Text, nullable=True),
    )

    # Categories
    op.create_table(
        "categories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("keywords", JSONB, nullable=True),
        sa.Column("url_patterns", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
    )

    # Credentials
    op.create_table(
        "credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False, unique=True),
        sa.Column("login_url", sa.Text, nullable=True),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.Text, nullable=False),
        sa.Column("username_selector", sa.String(255), nullable=True),
        sa.Column("password_selector", sa.String(255), nullable=True),
        sa.Column("submit_selector", sa.String(255), nullable=True),
        sa.Column("extra_auth_data", sa.Text, nullable=True),
    )
    op.create_index("ix_credentials_domain", "credentials", ["domain"])

    # Scrape Results
    op.create_table(
        "scrape_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("content", JSONB, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("page_title", sa.Text, nullable=True),
        sa.Column("content_length", sa.Integer, default=0, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_scrape_results_job_id", "scrape_results", ["job_id"])
    op.create_index("ix_scrape_results_url", "scrape_results", ["url"])
    op.create_index("ix_scrape_results_content_hash", "scrape_results", ["content_hash"])

    # Content Versions
    op.create_table(
        "content_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scrape_result_id", UUID(as_uuid=True), sa.ForeignKey("scrape_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("is_snapshot", sa.Boolean, default=False, nullable=False),
        sa.Column("full_content", JSONB, nullable=True),
        sa.Column("diff_content", JSONB, nullable=True),
        sa.Column("change_summary", sa.Text, nullable=True),
        sa.Column("blocks_changed", sa.Integer, default=0, nullable=False),
    )
    op.create_index("ix_content_versions_scrape_result_id", "content_versions", ["scrape_result_id"])

    # Log Entries
    op.create_table(
        "log_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Enum("debug", "info", "warning", "error", "critical", name="log_level_enum"), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("component", sa.String(100), nullable=True),
    )
    op.create_index("ix_log_entries_job_id", "log_entries", ["job_id"])


def downgrade() -> None:
    op.drop_table("log_entries")
    op.drop_table("content_versions")
    op.drop_table("scrape_results")
    op.drop_table("credentials")
    op.drop_table("categories")
    op.drop_table("jobs")

    op.execute("DROP TYPE IF EXISTS crawl_mode_enum")
    op.execute("DROP TYPE IF EXISTS job_status_enum")
    op.execute("DROP TYPE IF EXISTS log_level_enum")
