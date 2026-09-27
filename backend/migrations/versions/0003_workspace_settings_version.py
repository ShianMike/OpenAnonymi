"""Add optimistic versioning for workspace defaults."""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE workspaces ADD COLUMN settings_version integer NOT NULL DEFAULT 1")
    op.execute(
        "ALTER TABLE workspaces ADD CONSTRAINT positive_workspace_settings_version "
        "CHECK (settings_version > 0)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE workspaces DROP CONSTRAINT positive_workspace_settings_version")
    op.execute("ALTER TABLE workspaces DROP COLUMN settings_version")
