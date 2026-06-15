"""add parent_revision_id to cover_letter_revisions for refine branching."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "011_add_revision_parent"
down_revision = "010_add_cover_letter_started_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cover_letter_revisions",
        sa.Column("parent_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cl_revision_parent",
        "cover_letter_revisions",
        "cover_letter_revisions",
        ["parent_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_cl_revision_parent", "cover_letter_revisions", type_="foreignkey")
    op.drop_column("cover_letter_revisions", "parent_revision_id")
