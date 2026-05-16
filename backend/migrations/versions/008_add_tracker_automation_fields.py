"""add cover_letter_id and source to job_applications."""

import sqlalchemy as sa
from alembic import op

revision = "008_add_tracker_automation_fields"
down_revision = "007_add_lifecycle_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_applications",
        sa.Column("cover_letter_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
    )
    op.create_foreign_key(
        "fk_job_applications_cover_letter_id",
        "job_applications",
        "cover_letters",
        ["cover_letter_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_job_applications_cover_letter_id",
        "job_applications",
        ["cover_letter_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_applications_cover_letter_id", table_name="job_applications")
    op.drop_constraint(
        "fk_job_applications_cover_letter_id", "job_applications", type_="foreignkey"
    )
    op.drop_column("job_applications", "source")
    op.drop_column("job_applications", "cover_letter_id")
