"""Workspace rule versions and review settings snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workspace_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("version >= 1", name="valid_workspace_rule_version"),
    )
    op.create_table(
        "rule_versions",
        sa.Column(
            "rule_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspace_rules.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("payload_key_id", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "document_rule_snapshots",
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("settings_version", sa.Integer(), primary_key=True),
        sa.Column("rule_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_id", "rule_version"],
            ["rule_versions.rule_id", "rule_versions.version"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("settings_version >= 1", name="valid_rule_snapshot_settings_version"),
    )


def downgrade():
    op.drop_table("document_rule_snapshots")
    op.drop_table("rule_versions")
    op.drop_table("workspace_rules")
