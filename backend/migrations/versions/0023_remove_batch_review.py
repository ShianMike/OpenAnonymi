"""Retire batch metadata and its queue, preserving every individual review."""

from importlib import import_module

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("scan_jobs")
    op.drop_constraint("document_batch_pair", "documents", type_="check")
    op.drop_constraint("uq_documents_id_batch", "documents", type_="unique")
    op.drop_constraint("uq_documents_batch_position", "documents", type_="unique")
    op.drop_constraint("fk_documents_batch_owner", "documents", type_="foreignkey")
    op.drop_column("documents", "batch_position")
    op.drop_column("documents", "batch_id")
    op.drop_table("batches")
    op.execute("DROP FUNCTION protect_batch_snapshot()")
    op.execute("DELETE FROM audit_events WHERE event_code IN ('batch_created', 'batch_deleted')")


def downgrade():
    # Schema rollback cannot restore removed grouping, names or queued work.
    import_module("migrations.versions.0018_batch_review").upgrade()
