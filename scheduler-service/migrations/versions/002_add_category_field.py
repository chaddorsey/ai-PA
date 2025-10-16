"""Add category field to jobs table for reminder categorization.

Revision ID: 002_add_category_field
Revises: 001_create_scheduler_schema
Create Date: 2025-10-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "002_add_category_field"
down_revision: Union[str, None] = "001_create_scheduler_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add category column to jobs table."""
    op.add_column(
        "jobs",
        sa.Column("category", sa.String(length=128), nullable=True),
        schema="scheduler",
    )

    # Add index for filtering by category
    op.create_index(
        "jobs_category_idx",
        "jobs",
        ["category"],
        schema="scheduler",
    )


def downgrade() -> None:
    """Remove category column from jobs table."""
    op.drop_index("jobs_category_idx", table_name="jobs", schema="scheduler")
    op.drop_column("jobs", "category", schema="scheduler")



