#======================================================================================================
# Add scrape_result_categories join table for many-to-many classification.
#
# This migration adds:
#   - scrape_result_categories table (scrape_result_id, category_id)
#
# Revision:             0002
# Down revision:        0001_initial
#======================================================================================================

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_result_categories",

        sa.Column(
            "scrape_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "scrape_results.id",
                ondelete="CASCADE",
                name="fk_src_scrape_result_id",
            ),
            primary_key=True,
            nullable=False,
        ),

        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "categories.id",
                ondelete="RESTRICT",
                name="fk_src_category_id",
            ),
            primary_key=True,
            nullable=False,
        ),
    )

    # Index on category_id so "which results belong to category X?" is fast.
    op.create_index(
        "ix_scrape_result_categories_category_id",
        "scrape_result_categories",
        ["category_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scrape_result_categories_category_id",
        table_name="scrape_result_categories",
    )
    op.drop_table("scrape_result_categories")
