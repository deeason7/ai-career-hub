"""Add deadline column to job_applications table.

Revision ID: 002_add_deadline_to_jobs
Revises: 001_enable_rls
Create Date: 2026-03-27
"""
import sqlalchemy as sa
from alembic import op

revision = "002_add_deadline_to_jobs"
down_revision = "001_enable_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_applications",
        sa.Column("deadline", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_applications", "deadline")
