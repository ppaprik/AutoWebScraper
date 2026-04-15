#======================================================================================================
# Add js_mode column to jobs table

# Revision ID: 0004_job_js_mode
# Revises: 0003
# Create Date: 2026-04-09
#======================================================================================================

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_job_js_mode"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    js_mode_enum = sa.Enum(
        "auto", "always", "never",
        name="js_mode_enum",
    )
    js_mode_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "jobs",
        sa.Column(
            "js_mode",
            js_mode_enum,
            nullable=False,
            server_default="auto",
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "js_mode")
    op.execute("DROP TYPE IF EXISTS js_mode_enum")
