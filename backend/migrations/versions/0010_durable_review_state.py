"""Persist content-free attempt accounting and review undo."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def protect():
    # Identifier quoting happens on the server; every table, including Alembic's
    # version table, denies hosted public API roles even when grants were inherited.
    op.execute("""DO $$ DECLARE t record; r text; BEGIN
        FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', t.tablename);
            FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=r) THEN
                    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', t.tablename, r);
                END IF;
            END LOOP;
        END LOOP;
    END $$;""")


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "attempt_events",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("subject_hmac", sa.LargeBinary(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("octet_length(subject_hmac) = 32", name="attempt_subject_digest_length"),
    )
    op.create_index(
        "ix_attempt_subject_window", "attempt_events", ["scope", "subject_hmac", "attempted_at"]
    )
    op.create_table(
        "review_undo_entries",
        sa.Column("id", uuid, primary_key=True),
        sa.Column(
            "document_id", uuid, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("actor_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("after_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "actor_id", "sequence", name="uq_review_undo_sequence"),
        sa.CheckConstraint("sequence > 0 AND after_version >= 0", name="valid_review_undo_version"),
        sa.CheckConstraint(
            "payload_bytes > 0 AND payload_bytes <= 524288", name="bounded_review_undo_payload"
        ),
    )
    op.create_index(
        "ix_review_undo_actor_sequence",
        "review_undo_entries",
        ["document_id", "actor_id", "sequence"],
    )
    protect()


def downgrade():
    op.drop_table("review_undo_entries")
    op.drop_table("attempt_events")
