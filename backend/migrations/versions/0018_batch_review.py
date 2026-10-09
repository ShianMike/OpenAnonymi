"""Encrypted owner batches and durable version-bound scan leases."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "batches",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name_ciphertext", sa.LargeBinary()),
        sa.Column("name_key_id", sa.String(80)),
        sa.Column("column_rules_ciphertext", sa.LargeBinary()),
        sa.Column("column_rules_key_id", sa.String(80)),
        sa.Column("settings", JSONB(), nullable=False),
        sa.Column("uploaded_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "owner_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_batches_owner_membership",
        ),
        sa.UniqueConstraint("id", "workspace_id", "owner_id", name="uq_batches_owner_workspace"),
        sa.CheckConstraint("uploaded_bytes BETWEEN 0 AND 41943040", name="bounded_batch_bytes"),
        sa.CheckConstraint(
            "jsonb_typeof(settings)='object' AND octet_length(settings::text)<=131072",
            name="bounded_batch_settings",
        ),
        sa.CheckConstraint(
            "(name_ciphertext IS NULL AND name_key_id IS NULL) OR (name_ciphertext IS NOT NULL AND name_key_id IS NOT NULL)",
            name="batch_name_encryption_pair",
        ),
        sa.CheckConstraint(
            "(column_rules_ciphertext IS NULL AND column_rules_key_id IS NULL) OR (column_rules_ciphertext IS NOT NULL AND column_rules_key_id IS NOT NULL)",
            name="batch_columns_encryption_pair",
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR deleted_at>=created_at", name="batch_delete_after_creation"
        ),
    )
    op.create_index("ix_batches_owner_created", "batches", ["owner_id", "created_at"])
    op.add_column("documents", sa.Column("batch_id", sa.UUID()))
    op.add_column("documents", sa.Column("batch_position", sa.Integer()))
    op.create_foreign_key(
        "fk_documents_batch_owner",
        "documents",
        "batches",
        ["batch_id", "workspace_id", "owner_id"],
        ["id", "workspace_id", "owner_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_documents_batch_position", "documents", ["batch_id", "batch_position"]
    )
    op.create_unique_constraint("uq_documents_id_batch", "documents", ["id", "batch_id"])
    op.create_check_constraint(
        "document_batch_pair",
        "documents",
        "(batch_id IS NULL AND batch_position IS NULL) OR (batch_id IS NOT NULL AND batch_position IS NOT NULL AND batch_position BETWEEN 1 AND 20)",
    )
    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_id", sa.UUID(), sa.ForeignKey("batches.id", ondelete="CASCADE")),
        sa.Column("source_revision_id", sa.UUID(), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("lease_owner", sa.UUID()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(40)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "source_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            ondelete="CASCADE",
            name="fk_scan_jobs_revision",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "batch_id"],
            ["documents.id", "documents.batch_id"],
            ondelete="CASCADE",
            name="fk_scan_jobs_document_batch",
        ),
        sa.UniqueConstraint(
            "document_id", "source_revision_id", "settings_version", name="uq_scan_jobs_input"
        ),
        sa.CheckConstraint(
            "settings_version>=1 AND attempts>=0", name="valid_scan_job_version_attempts"
        ),
        sa.CheckConstraint(
            "status IN ('queued','leased','done','failed','skipped')", name="valid_scan_job_status"
        ),
        sa.CheckConstraint(
            "(status='leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status<>'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="scan_job_lease_pair",
        ),
    )
    op.create_index("ix_scan_jobs_claim", "scan_jobs", ["status", "available_at", "created_at"])
    op.execute("""CREATE FUNCTION protect_batch_snapshot() RETURNS trigger AS $$ BEGIN
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.settings IS DISTINCT FROM OLD.settings
        OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
        OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.uploaded_bytes < OLD.uploaded_bytes
        OR (OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS DISTINCT FROM OLD.deleted_at)
      THEN RAISE EXCEPTION 'Batch snapshot is immutable'; END IF;
      IF (NEW.name_ciphertext IS DISTINCT FROM OLD.name_ciphertext OR NEW.name_key_id IS DISTINCT FROM OLD.name_key_id
          OR NEW.column_rules_ciphertext IS DISTINCT FROM OLD.column_rules_ciphertext OR NEW.column_rules_key_id IS DISTINCT FROM OLD.column_rules_key_id)
        AND current_setting('openanonymi.key_rotation',true) IS DISTINCT FROM 'on'
        AND NOT (NEW.deleted_at IS NOT NULL AND NEW.name_ciphertext IS NULL AND NEW.name_key_id IS NULL
          AND NEW.column_rules_ciphertext IS NULL AND NEW.column_rules_key_id IS NULL)
      THEN RAISE EXCEPTION 'Batch protected snapshot is immutable'; END IF;
      RETURN NEW; END; $$ LANGUAGE plpgsql""")
    op.execute(
        "CREATE TRIGGER batch_snapshot_immutable BEFORE UPDATE ON batches FOR EACH ROW EXECUTE FUNCTION protect_batch_snapshot()"
    )
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM batches) OR EXISTS (SELECT 1 FROM scan_jobs)
      OR EXISTS (SELECT 1 FROM documents WHERE batch_id IS NOT NULL OR batch_position IS NOT NULL)
      THEN RAISE EXCEPTION 'Batch review data must be preserved; downgrade refused'; END IF; END $$""")
    op.drop_table("scan_jobs")
    op.drop_constraint("document_batch_pair", "documents", type_="check")
    op.drop_constraint("uq_documents_id_batch", "documents", type_="unique")
    op.drop_constraint("uq_documents_batch_position", "documents", type_="unique")
    op.drop_constraint("fk_documents_batch_owner", "documents", type_="foreignkey")
    op.drop_column("documents", "batch_position")
    op.drop_column("documents", "batch_id")
    op.drop_table("batches")
    op.execute("DROP FUNCTION protect_batch_snapshot()")
