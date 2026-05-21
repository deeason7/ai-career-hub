"""Add cover_letter_revisions table.

Revision ID: 006_add_cover_letter_revisions
Revises: 005_drop_user_role
Create Date: 2026-05-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006_add_cover_letter_revisions"
down_revision = "005_drop_user_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cover_letter_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cover_letter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cover_letters.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("generated_text", sa.Text(), nullable=False),
        sa.Column("user_command", sa.Text(), nullable=False),
        sa.Column("qa_score_honesty", sa.Integer(), nullable=True),
        sa.Column("qa_score_tone", sa.Integer(), nullable=True),
        sa.Column("qa_flags", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cover_letter_id", "version_number", name="uq_cl_revision_version"),
    )


def downgrade() -> None:
    op.drop_table("cover_letter_revisions")
