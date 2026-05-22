"""Add lifecycle fields (is_permanent, expires_at) to resumes and cover_letters."""

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
