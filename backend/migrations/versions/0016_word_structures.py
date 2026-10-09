"""Encrypted Word/CSV revision structure, boundary scan count and DOCX exports."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_structures",
        sa.Column(
            "revision_id",
            sa.UUID(),
            sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("layout_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("block_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('docx','csv')", name="valid_kind"),
        sa.CheckConstraint("block_count BETWEEN 1 AND 20000", name="bounded_block_count"),
    )
    op.execute("""CREATE FUNCTION protect_source_structure() RETURNS trigger AS $$ BEGIN
      IF current_setting('openanonymi.key_rotation',true) IS DISTINCT FROM 'on'
        OR NEW.revision_id IS DISTINCT FROM OLD.revision_id OR NEW.kind IS DISTINCT FROM OLD.kind
        OR NEW.block_count IS DISTINCT FROM OLD.block_count OR NEW.created_at IS DISTINCT FROM OLD.created_at
      THEN RAISE EXCEPTION 'Source layouts are immutable'; END IF;
      RETURN NEW; END; $$ LANGUAGE plpgsql""")
    op.execute(
        "CREATE TRIGGER source_structure_immutable BEFORE UPDATE ON source_structures FOR EACH ROW EXECUTE FUNCTION protect_source_structure()"
    )
    op.add_column(
        "scan_runs",
        sa.Column("dropped_suggestions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "nonnegative_dropped_suggestions", "scan_runs", "dropped_suggestions >= 0"
    )
    op.drop_constraint("valid_format", "export_events", type_="check")
    op.create_check_constraint("valid_format", "export_events", "format IN ('copy','txt','docx')")
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM source_structures)
      OR EXISTS (SELECT 1 FROM export_events WHERE format='docx')
      OR EXISTS (SELECT 1 FROM scan_runs WHERE dropped_suggestions>0)
      THEN RAISE EXCEPTION 'Structured review data must be preserved; downgrade refused'; END IF; END $$""")
    op.drop_constraint("valid_format", "export_events", type_="check")
    op.create_check_constraint("valid_format", "export_events", "format IN ('copy','txt')")
    op.drop_constraint("nonnegative_dropped_suggestions", "scan_runs", type_="check")
    op.drop_column("scan_runs", "dropped_suggestions")
    op.drop_table("source_structures")
    op.execute("DROP FUNCTION protect_source_structure()")
