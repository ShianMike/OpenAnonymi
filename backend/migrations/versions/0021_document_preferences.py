"""Persist personal document flags without granting content access."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_preferences",
        sa.Column(
            "actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint("favorite OR pinned", name="nonempty_document_preference"),
    )
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM document_preferences)
      THEN RAISE EXCEPTION 'Personal document preferences must be preserved; downgrade refused';
      END IF; END $$""")
    op.drop_table("document_preferences")
