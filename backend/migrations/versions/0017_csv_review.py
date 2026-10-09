"""Protected CSV column snapshots, current syntax settings and reviewed exports."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

DELIMITERS = "csv_delimiter IN (',',';',E'\\t','|')"


def upgrade():
    op.add_column("documents", sa.Column("csv_delimiter", sa.String(1)))
    op.add_column("documents", sa.Column("csv_has_header", sa.Boolean()))
    op.create_check_constraint(
        "csv_settings_pair",
        "documents",
        "(csv_delimiter IS NULL AND csv_has_header IS NULL) OR "
        "(csv_delimiter IS NOT NULL AND csv_has_header IS NOT NULL AND " + DELIMITERS + ")",
    )
    op.add_column("presets", sa.Column("column_rules_ciphertext", sa.LargeBinary()))
    op.add_column("presets", sa.Column("column_rules_key_id", sa.String(80)))
    op.create_check_constraint(
        "column_rules_encryption_pair",
        "presets",
        "(column_rules_ciphertext IS NULL AND column_rules_key_id IS NULL) OR "
        "(column_rules_ciphertext IS NOT NULL AND column_rules_key_id IS NOT NULL)",
    )
    op.create_table(
        "document_column_rules",
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("settings_version", sa.Integer(), primary_key=True),
        sa.Column("rules_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("csv_delimiter", sa.String(1), nullable=False),
        sa.Column("csv_has_header", sa.Boolean(), nullable=False),
        sa.CheckConstraint("settings_version>=1", name="positive_column_settings_version"),
        sa.CheckConstraint(DELIMITERS, name="valid_column_delimiter"),
    )
    op.execute("""CREATE FUNCTION protect_column_rules() RETURNS trigger AS $$ BEGIN
      IF current_setting('openanonymi.key_rotation',true) IS DISTINCT FROM 'on'
        OR NEW.document_id IS DISTINCT FROM OLD.document_id
        OR NEW.settings_version IS DISTINCT FROM OLD.settings_version
        OR NEW.csv_delimiter IS DISTINCT FROM OLD.csv_delimiter
        OR NEW.csv_has_header IS DISTINCT FROM OLD.csv_has_header
      THEN RAISE EXCEPTION 'Column rule snapshots are immutable'; END IF;
      RETURN NEW; END; $$ LANGUAGE plpgsql""")
    op.execute(
        "CREATE TRIGGER column_rules_immutable BEFORE UPDATE ON document_column_rules FOR EACH ROW EXECUTE FUNCTION protect_column_rules()"
    )
    op.drop_constraint("bounded_block_count", "source_structures", type_="check")
    op.create_check_constraint(
        "bounded_block_count",
        "source_structures",
        "block_count >= 1 AND ((kind='docx' AND block_count<=20000) OR (kind='csv' AND block_count<=50050))",
    )
    op.drop_constraint("valid_format", "export_events", type_="check")
    op.create_check_constraint(
        "valid_format", "export_events", "format IN ('copy','txt','docx','csv')"
    )
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM source_structures WHERE kind='csv')
      OR EXISTS (SELECT 1 FROM document_column_rules)
      OR EXISTS (SELECT 1 FROM presets WHERE column_rules_ciphertext IS NOT NULL)
      OR EXISTS (SELECT 1 FROM documents WHERE csv_delimiter IS NOT NULL)
      OR EXISTS (SELECT 1 FROM export_events WHERE format='csv')
      THEN RAISE EXCEPTION 'CSV review data must be preserved; downgrade refused'; END IF; END $$""")
    op.drop_constraint("valid_format", "export_events", type_="check")
    op.create_check_constraint("valid_format", "export_events", "format IN ('copy','txt','docx')")
    op.drop_constraint("bounded_block_count", "source_structures", type_="check")
    op.create_check_constraint(
        "bounded_block_count", "source_structures", "block_count BETWEEN 1 AND 20000"
    )
    op.drop_table("document_column_rules")
    op.execute("DROP FUNCTION protect_column_rules()")
    op.drop_constraint("column_rules_encryption_pair", "presets", type_="check")
    op.drop_column("presets", "column_rules_key_id")
    op.drop_column("presets", "column_rules_ciphertext")
    op.drop_constraint("csv_settings_pair", "documents", type_="check")
    op.drop_column("documents", "csv_has_header")
    op.drop_column("documents", "csv_delimiter")
