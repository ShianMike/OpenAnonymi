"""Bounded fixed decision metadata in the existing content-free activity history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_events",
        sa.Column(
            "decision_changes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "audit_events",
        sa.Column("decision_change_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("audit_events", sa.Column("decision_version", sa.Integer()))
    op.create_check_constraint(
        "bounded_audit_decision_changes",
        "audit_events",
        "jsonb_typeof(decision_changes)='array' AND octet_length(decision_changes::text)<=262144",
    )
    op.create_check_constraint(
        "valid_audit_change_count",
        "audit_events",
        "decision_change_count>=0 AND decision_change_count>=jsonb_array_length(decision_changes) AND jsonb_array_length(decision_changes)<=256",
    )
    op.create_check_constraint(
        "valid_audit_decision_version",
        "audit_events",
        "decision_version IS NULL OR decision_version>=0",
    )


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM audit_events WHERE decision_change_count>0 OR decision_version IS NOT NULL)
      THEN RAISE EXCEPTION 'Decision audit history must be preserved; downgrade refused'; END IF; END $$""")
    for name in (
        "valid_audit_decision_version",
        "valid_audit_change_count",
        "bounded_audit_decision_changes",
    ):
        op.drop_constraint(name, "audit_events", type_="check")
    for name in ("decision_version", "decision_change_count", "decision_changes"):
        op.drop_column("audit_events", name)
