#======================================================================================================
# Add filter_category_ids column to the jobs table.
#
# This column stores a JSON list of category UUIDs that act as a content
# filter: only pages classified into any of these categories are saved
# (OR logic). An empty or NULL value means "save everything".
#
# Revision:      0003
# Down revision: 0002
#======================================================================================================

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "filter_category_ids",
            sa.JSON,
            nullable=True,
            comment=(
                "JSON list of category UUID strings for content filtering. "
                "NULL or [] means save all pages regardless of category."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "filter_category_ids")
