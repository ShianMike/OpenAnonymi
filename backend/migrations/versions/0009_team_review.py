"""Explicit document reviewer grants, exact-version approval and encrypted notes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "review_handoffs",
        sa.Column(
            "document_id", uuid, sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("reviewer_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("require_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("generation > 0", name="positive_handoff_generation"),
    )
    op.create_table(
        "review_approvals",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "document_id", uuid, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column(
            "source_revision_id",
            uuid,
            sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_version", sa.Integer(), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column(
            "approved_by", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "approved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "document_id",
            "generation",
            "source_revision_id",
            "decision_version",
            "settings_version",
            name="uq_review_approval_version",
        ),
        sa.CheckConstraint(
            "generation > 0 AND decision_version >= 0 AND settings_version > 0",
            name="valid_approval_version",
        ),
    )
    op.create_table(
        "finding_comments",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "document_id", uuid, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "finding_id", uuid, sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "author_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("text_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("text_key_id", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_finding_comments_document_id", "finding_comments", ["document_id"])
    op.create_index("ix_finding_comments_finding_id", "finding_comments", ["finding_id"])


def downgrade():
    op.drop_table("finding_comments")
    op.drop_table("review_approvals")
    op.drop_table("review_handoffs")
