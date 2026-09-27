"""Persist version-bound scan runs and explainable automatic suggestions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("source_revision_id", sa.UUID(), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("detector_version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=40), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("settings_version > 0", name="positive_scan_settings_version"),
        sa.CheckConstraint("attempt_count > 0", name="positive_scan_attempt_count"),
        sa.CheckConstraint(
            "match_count IS NULL OR match_count >= 0", name="nonnegative_scan_match_count"
        ),
        sa.CheckConstraint(
            "status IN ('scanning', 'completed', 'failed', 'superseded')", name="valid_scan_status"
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "source_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "source_revision_id", "settings_version", name="uq_scan_runs_input"
        ),
        sa.UniqueConstraint(
            "document_id", "source_revision_id", "id", name="uq_scan_runs_revision_id"
        ),
    )
    op.add_column("findings", sa.Column("reason", sa.String(length=200), nullable=True))
    op.add_column("findings", sa.Column("scan_run_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_findings_scan_run",
        "findings",
        "scan_runs",
        ["document_id", "source_revision_id", "scan_run_id"],
        ["document_id", "source_revision_id", "id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "automatic_finding_metadata",
        "findings",
        "(origin = 'manual' AND scan_run_id IS NULL) OR "
        "(origin = 'automatic' AND scan_run_id IS NOT NULL AND rule_id IS NOT NULL "
        "AND rule_version IS NOT NULL AND reason IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("automatic_finding_metadata", "findings", type_="check")
    op.drop_constraint("fk_findings_scan_run", "findings", type_="foreignkey")
    op.drop_column("findings", "scan_run_id")
    op.drop_column("findings", "reason")
    op.drop_table("scan_runs")
