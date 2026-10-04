"""Workspace output policy and content-free recipient notifications."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspaces",
        sa.Column("approval_policy", sa.String(12), nullable=False, server_default="owner_choice"),
    )
    op.create_check_constraint(
        "valid_approval_policy", "workspaces", "approval_policy IN ('owner_choice','always')"
    )
    op.add_column(
        "users",
        sa.Column("notification_emails", sa.String(9), nullable=False, server_default="off"),
    )
    op.create_check_constraint(
        "valid_notification_emails", "users", "notification_emails IN ('off','immediate')"
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.UUID(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE")),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_code", sa.String(24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("email_status", sa.String(16), nullable=False, server_default="not_requested"),
        sa.Column("email_attempted_at", sa.DateTime(timezone=True)),
        sa.Column("email_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint(
            "event_code IN ('review_assigned','review_unassigned','approval_requested','review_approved','approval_invalidated','comment_added')",
            name="valid_notification_event",
        ),
        sa.CheckConstraint(
            "email_status IN ('not_requested','sent','failed','skipped_limit')",
            name="valid_notification_delivery",
        ),
        sa.CheckConstraint(
            "email_status='not_requested' OR email_attempted_at IS NOT NULL",
            name="notification_delivery_attempt",
        ),
        sa.CheckConstraint(
            "read_at IS NULL OR read_at >= created_at", name="notification_read_after_created"
        ),
    )
    op.create_index(
        "ix_notifications_recipient_order", "notifications", ["recipient_id", "created_at", "id"]
    )
    op.create_index("ix_notifications_document", "notifications", ["document_id"])
    op.create_index(
        "ix_notifications_delivery",
        "notifications",
        ["email_requested", "email_attempted_at", "created_at"],
    )
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM notifications)
      OR EXISTS (SELECT 1 FROM workspaces WHERE approval_policy <> 'owner_choice')
      OR EXISTS (SELECT 1 FROM users WHERE notification_emails <> 'off')
      THEN RAISE EXCEPTION 'Approval policy and notification data must be preserved; downgrade refused'; END IF; END $$""")
    op.drop_table("notifications")
    op.drop_constraint("valid_notification_emails", "users", type_="check")
    op.drop_column("users", "notification_emails")
    op.drop_constraint("valid_approval_policy", "workspaces", type_="check")
    op.drop_column("workspaces", "approval_policy")
