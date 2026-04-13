"""Add QA review columns to cover_letters table.

Revision ID: 004_add_qa_columns
Revises: 003_fix_rls_policies
Create Date: 2026-04-13

Milestone 1: AI-as-a-Judge QA Layer
Adds nullable columns for honesty/tone scores, flags (JSON text), and
retry count to track how many regeneration attempts were needed.
"""
import sqlalchemy as sa
from alembic import op

revision = "004_add_qa_columns"
down_revision = "003_fix_rls_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cover_letters", sa.Column("qa_score_honesty", sa.Integer(), nullable=True))
    op.add_column("cover_letters", sa.Column("qa_score_tone", sa.Integer(), nullable=True))
    op.add_column("cover_letters", sa.Column("qa_flags", sa.Text(), nullable=True))
    op.add_column("cover_letters", sa.Column("qa_retries", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("cover_letters", "qa_retries")
    op.drop_column("cover_letters", "qa_flags")
    op.drop_column("cover_letters", "qa_score_tone")
    op.drop_column("cover_letters", "qa_score_honesty")
