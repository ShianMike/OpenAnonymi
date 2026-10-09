"""Prove email ownership before self-registration creates an account."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("canonical_email", sa.String(320), nullable=False),
        sa.Column("code_digest", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("workspace_name_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("octet_length(code_digest) = 32", name="registration_digest_length"),
        sa.CheckConstraint("expires_at > created_at", name="registration_expiry"),
    )
    op.create_index(
        "ix_pending_registration_address_expiry",
        "pending_registrations",
        ["canonical_email", "expires_at"],
    )
    op.create_table(
        "email_verifications",
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("code_digest", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("octet_length(code_digest) = 32", name="email_proof_digest_length"),
        sa.CheckConstraint("failed_attempts BETWEEN 0 AND 5", name="email_proof_failures"),
        sa.CheckConstraint("expires_at > created_at", name="email_proof_expiry"),
    )
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.drop_table("email_verifications")
    op.drop_table("pending_registrations")
    op.drop_column("users", "email_verified_at")
