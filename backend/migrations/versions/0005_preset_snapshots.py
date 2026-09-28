"""Save the effective preset and preferred review action at intake."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "presets",
        sa.Column("preferred_action", sa.String(8), nullable=False, server_default="label"),
    )
    op.create_check_constraint(
        "valid_preferred_action", "presets", "preferred_action IN ('label', 'redact')"
    )
    op.create_index(
        "uq_presets_workspace_default",
        "presets",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.add_column("documents", sa.Column("preset_id", sa.UUID(), nullable=True))
    op.add_column("documents", sa.Column("preset_version", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("preferred_action", sa.String(8), nullable=False, server_default="label"),
    )
    op.create_check_constraint(
        "valid_document_preset_snapshot",
        "documents",
        "(preset_id IS NULL AND preset_version IS NULL) OR (preset_id IS NOT NULL AND preset_version >= 1)",
    )
    op.create_check_constraint(
        "valid_preferred_action", "documents", "preferred_action IN ('label', 'redact')"
    )


def downgrade() -> None:
    op.drop_constraint("valid_preferred_action", "documents", type_="check")
    op.drop_constraint("valid_document_preset_snapshot", "documents", type_="check")
    op.drop_column("documents", "preferred_action")
    op.drop_column("documents", "preset_version")
    op.drop_column("documents", "preset_id")
    op.drop_index("uq_presets_workspace_default", table_name="presets")
    op.drop_constraint("valid_preferred_action", "presets", type_="check")
    op.drop_column("presets", "preferred_action")
