"""Add deadline column to job_applications table.

Revision ID: 002_add_deadline_to_jobs
Revises: 001_enable_rls
Create Date: 2026-03-27
"""
from alembic import op

revision = "002_add_deadline_to_jobs"
down_revision = "001_enable_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS makes this idempotent — safe to re-run on a DB that
    # already has the column (e.g. created via SQLModel create_all).
    op.execute(
        "ALTER TABLE job_applications ADD COLUMN IF NOT EXISTS deadline DATE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE job_applications DROP COLUMN IF EXISTS deadline"
    )
