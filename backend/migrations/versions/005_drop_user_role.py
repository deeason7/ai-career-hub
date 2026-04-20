"""Drop unused 'role' column from users table.

Revision ID: 005_drop_user_role
Revises: 004_add_qa_columns
Create Date: 2026-04-19

The `role` column was added in the initial schema but has never been read
or enforced anywhere in the application. Dropping it eliminates dead schema
and reduces confusion. If an admin-role feature is added in the future a
new migration should re-introduce the column with proper enforcement.
"""

import sqlalchemy as sa
from alembic import op

revision = "005_drop_user_role"
down_revision = "004_add_qa_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "role")


def downgrade() -> None:
    # Restore the column with its original default so existing rows stay valid.
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(),
            nullable=False,
            server_default="candidate",
        ),
    )
