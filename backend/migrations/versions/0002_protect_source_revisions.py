"""Guard immutable source revisions; allow controlled ciphertext key rotation."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION guard_source_revision_update() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('openanonymi.key_rotation', true) IS DISTINCT FROM 'on' THEN
                RAISE EXCEPTION 'Source revisions are immutable';
            END IF;
            IF ROW(NEW.id, NEW.document_id, NEW.revision_number,
                   NEW.utf8_bytes, NEW.code_points, NEW.created_at)
               IS DISTINCT FROM
               ROW(OLD.id, OLD.document_id, OLD.revision_number,
                   OLD.utf8_bytes, OLD.code_points, OLD.created_at) THEN
                RAISE EXCEPTION 'Key rotation cannot change source revision metadata';
            END IF;
            IF (NEW.source_ciphertext IS DISTINCT FROM OLD.source_ciphertext)
               IS DISTINCT FROM
               (NEW.source_key_id IS DISTINCT FROM OLD.source_key_id) THEN
                RAISE EXCEPTION 'Key rotation must replace both ciphertext and key identifier';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER source_revision_update_guard
        BEFORE UPDATE ON source_revisions
        FOR EACH ROW EXECUTE FUNCTION guard_source_revision_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER source_revision_update_guard ON source_revisions")
    op.execute("DROP FUNCTION guard_source_revision_update()")
