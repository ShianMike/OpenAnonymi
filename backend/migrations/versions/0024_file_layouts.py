"""Retain encrypted PDF layouts and literal text formatting."""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("valid_kind", "source_structures", type_="check")
    op.create_check_constraint(
        "valid_kind", "source_structures", "kind IN ('docx','csv','pdf','txt')"
    )
    op.drop_constraint("bounded_block_count", "source_structures", type_="check")
    op.create_check_constraint(
        "bounded_block_count",
        "source_structures",
        "block_count >= 1 AND ((kind='docx' AND block_count<=20000) OR (kind='csv' AND block_count<=50050) OR (kind IN ('pdf','txt') AND block_count<=100000))",
    )


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM source_structures WHERE kind IN ('pdf','txt'))
      THEN RAISE EXCEPTION 'File layouts must be preserved; downgrade refused'; END IF; END $$""")
    op.drop_constraint("valid_kind", "source_structures", type_="check")
    op.create_check_constraint("valid_kind", "source_structures", "kind IN ('docx','csv')")
    op.drop_constraint("bounded_block_count", "source_structures", type_="check")
    op.create_check_constraint(
        "bounded_block_count",
        "source_structures",
        "block_count >= 1 AND ((kind='docx' AND block_count<=20000) OR (kind='csv' AND block_count<=50050))",
    )
