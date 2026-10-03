"""Replacement style codes, encrypted document secrets and versioned defaults."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

STYLE_ACTION = "(action='label' AND style IN ('token','stand_in','date_shift')) OR (action='redact' AND style IN ('token','partial_mask','generalize')) OR (action='keep' AND style='token')"
STYLE_OPTION = "(style IN ('token','stand_in','date_shift') AND style_option IS NULL) OR (style='partial_mask' AND style_option IS NOT NULL AND style_option IN ('full','last4','first_letters','email_domain','email_first','url_host','secret_prefix')) OR (style='generalize' AND style_option IS NOT NULL AND style_option IN ('month_year','year','age_band'))"
DEFAULTS = (
    "jsonb_typeof(category_defaults)='object' AND octet_length(category_defaults::text)<=8192"
)


def upgrade():
    op.add_column(
        "decisions", sa.Column("style", sa.String(16), nullable=False, server_default="token")
    )
    op.add_column("decisions", sa.Column("style_option", sa.String(24), nullable=True))
    op.create_check_constraint("valid_action_style", "decisions", STYLE_ACTION)
    op.create_check_constraint("valid_style_option", "decisions", STYLE_OPTION)
    for table in ("presets", "documents"):
        op.add_column(
            table,
            sa.Column(
                "category_defaults", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
            ),
        )
        op.create_check_constraint("bounded_category_defaults", table, DEFAULTS)
    op.create_table(
        "document_replacement_secrets",
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    # Refuse a lossy downgrade when new decisions or replacement secrets exist.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM decisions WHERE style<>'token')
          OR EXISTS (SELECT 1 FROM document_replacement_secrets)
          OR EXISTS (SELECT 1 FROM documents WHERE category_defaults<>'{}'::jsonb)
          OR EXISTS (SELECT 1 FROM presets WHERE category_defaults<>'{}'::jsonb)
        THEN RAISE EXCEPTION 'Replacement styles must be preserved; downgrade refused.';
        END IF;
    END $$;""")
    op.drop_table("document_replacement_secrets")
    for table in ("documents", "presets"):
        op.drop_constraint("bounded_category_defaults", table, type_="check")
        op.drop_column(table, "category_defaults")
    op.drop_constraint("valid_style_option", "decisions", type_="check")
    op.drop_constraint("valid_action_style", "decisions", type_="check")
    op.drop_column("decisions", "style_option")
    op.drop_column("decisions", "style")
