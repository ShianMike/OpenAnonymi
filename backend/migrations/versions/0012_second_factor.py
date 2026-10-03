"""Authenticator enrollment, forced two-step challenges and revocable devices."""

from importlib import import_module

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "second_factor_reenroll_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column("require_second_factor", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute("UPDATE sessions SET last_seen_at = created_at")
    op.add_column(
        "sessions",
        sa.Column(
            "device_label",
            sa.String(100),
            nullable=False,
            server_default="Unknown browser · Unknown system",
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("auth_method", sa.String(24), nullable=False, server_default="password"),
    )
    op.create_check_constraint(
        "session_auth_method",
        "sessions",
        "auth_method IN ('password', 'password_totp', 'password_backup_code', 'enrollment')",
    )
    op.create_table(
        "user_second_factors",
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("last_used_step", sa.Integer(), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_limit_notice_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('pending', 'active')", name="second_factor_status"),
        sa.CheckConstraint("failed_attempts BETWEEN 0 AND 100", name="second_factor_failures"),
        sa.CheckConstraint(
            "last_used_step IS NULL OR last_used_step >= 0", name="second_factor_step"
        ),
    )
    op.create_table(
        "user_backup_codes",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("code_digest", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("octet_length(code_digest) = 32", name="backup_code_digest_length"),
    )
    op.create_index("ix_backup_codes_user", "user_backup_codes", ["user_id"])
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_digest", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('second_factor', 'enrollment')", name="auth_challenge_kind"),
        sa.CheckConstraint("failed_attempts BETWEEN 0 AND 5", name="auth_challenge_failures"),
        sa.CheckConstraint("octet_length(token_digest) = 32", name="auth_challenge_digest_length"),
        sa.CheckConstraint("expires_at > created_at", name="auth_challenge_expiry"),
    )
    op.create_index("ix_auth_challenges_user_expiry", "auth_challenges", ["user_id", "expires_at"])
    import_module("migrations.versions.0010_durable_review_state").protect()


def downgrade():
    op.drop_table("auth_challenges")
    op.drop_table("user_backup_codes")
    op.drop_table("user_second_factors")
    op.drop_constraint("session_auth_method", "sessions", type_="check")
    for column in ("auth_method", "device_label", "last_seen_at"):
        op.drop_column("sessions", column)
    op.drop_column("workspaces", "require_second_factor")
    op.drop_column("users", "second_factor_reenroll_required")
