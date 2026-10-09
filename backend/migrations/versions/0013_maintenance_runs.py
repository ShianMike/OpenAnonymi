"""Content-free cleanup run health, shared by every maintenance trigger."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("trigger", sa.String(8), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("failure_code", sa.String(24), nullable=True),
        sa.Column("documents_purged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expired_rows_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activity_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "trigger IN ('startup','periodic','cli','endpoint')", name="maintenance_trigger"
        ),
        sa.CheckConstraint("status IN ('running','ok','failed')", name="maintenance_status"),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code IN ('abandoned','cleanup_failed')",
            name="maintenance_failure_code",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="maintenance_clock"
        ),
        sa.CheckConstraint(
            "documents_purged >= 0 AND expired_rows_removed >= 0 AND activity_removed >= 0",
            name="maintenance_counts",
        ),
    )
    op.create_index("ix_maintenance_started", "maintenance_runs", ["started_at", "id"])
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.drop_table("maintenance_runs")
