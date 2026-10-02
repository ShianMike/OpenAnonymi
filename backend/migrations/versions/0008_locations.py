"""Add a distinct location category without treating places as street addresses."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

CATEGORIES = "'person', 'organization', 'address', 'identifier', 'custom', 'email', 'phone'"


def upgrade():
    for table in ("findings", "entity_groups"):
        op.drop_constraint("valid_category", table, type_="check")
        op.create_check_constraint(
            "valid_category", table, f"category IN ({CATEGORIES}, 'location')"
        )


def downgrade():
    # Refuse downgrading with location rows rather than silently recategorizing.
    for table in ("findings", "entity_groups"):
        op.drop_constraint("valid_category", table, type_="check")
        op.create_check_constraint("valid_category", table, f"category IN ({CATEGORIES})")
