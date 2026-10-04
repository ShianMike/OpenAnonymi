"""Allow reviewed PDF/report events without discarding older output history."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("valid_format", "export_events", type_="check")
    op.create_check_constraint(
        "valid_format", "export_events", "format IN ('copy','txt','docx','csv','pdf','report')"
    )


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM export_events WHERE format IN ('pdf','report'))
      THEN RAISE EXCEPTION 'Reviewed PDF/report history must be preserved; downgrade refused';
      END IF; END $$""")
    op.drop_constraint("valid_format", "export_events", type_="check")
    op.create_check_constraint(
        "valid_format", "export_events", "format IN ('copy','txt','docx','csv')"
    )
