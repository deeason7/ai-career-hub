"""add audit_logs table."""

import sqlalchemy as sa
from alembic import op

revision = "009_add_audit_logs"
down_revision = "008_add_tracker_automation_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("event", sa.String(length=100), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_event", "audit_logs", ["event"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_event", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
