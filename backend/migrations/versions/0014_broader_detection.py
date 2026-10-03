"""New opt-in categories and content-free scan language/date format metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

OLD = "category IN ('person', 'organization', 'address', 'identifier', 'custom', 'email', 'phone', 'location')"
NEW = "category IN ('person', 'organization', 'address', 'identifier', 'custom', 'email', 'phone', 'location', 'date', 'url', 'secret', 'national_id')"


def categories(expression):
    for table in ('entity_groups', 'findings'):
        op.drop_constraint('valid_category', table, type_='check')
        op.create_check_constraint('valid_category', table, expression)


def upgrade():
    categories(NEW)
    op.add_column('documents', sa.Column('language', sa.String(2), nullable=False, server_default='en'))
    op.add_column('findings', sa.Column('date_format', sa.String(80), nullable=True))


def downgrade():
    # The transaction fails rather than deleting any new-category review data.
    categories(OLD)
    op.drop_column('findings', 'date_format')
    op.drop_column('documents', 'language')
