"""add started_at to cover_letters for the stuck-processing reaper."""

import sqlalchemy as sa
from alembic import op

revision = "010_add_cover_letter_started_at"
down_revision = "009_add_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cover_letters", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Backfill existing rows so the reaper can rely on started_at being present.
    op.execute("UPDATE cover_letters SET started_at = created_at WHERE started_at IS NULL")


def downgrade() -> None:
    op.drop_column("cover_letters", "started_at")
