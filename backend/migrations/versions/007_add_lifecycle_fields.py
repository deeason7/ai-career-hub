"""Add lifecycle fields to resumes and cover_letters tables.

Revision ID: 007_add_lifecycle_fields
Revises: 006_add_cover_letter_revisions
Create Date: 2026-05-16

Resumes: is_permanent, expires_at
  - Most recent resume per user is marked permanent on upload.
  - Older resumes receive expires_at = upload_time + 15 days.

Cover letters: expires_at
  - Cover letters expire 15 days after creation unless their
    linked resume is permanent.
"""

import sqlalchemy as sa
from alembic import op

revision = "007_add_lifecycle_fields"
down_revision = "006_add_cover_letter_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resumes", sa.Column("is_permanent", sa.Boolean(), nullable=False, server_default="false")
    )
    op.add_column("resumes", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "cover_letters", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("cover_letters", "expires_at")
    op.drop_column("resumes", "expires_at")
    op.drop_column("resumes", "is_permanent")
