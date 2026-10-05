"""Every app and migration table denies inherited public API grants."""

import io
import logging
from importlib import import_module

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def test_in_process_migration_keeps_security_notice_logging(monkeypatch):
    monkeypatch.setenv("PRIVACY_REVIEW_DATABASE_URL", "postgresql+psycopg://schema:schema@localhost/schema")
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("PRIVACY_REVIEW_ENVIRONMENT", "test")
    logger = logging.getLogger("app.accounts")
    monkeypatch.setattr(logger, "disabled", False)
    command.upgrade(Config("alembic.ini", output_buffer=io.StringIO()), "head", sql=True)
    assert not logger.disabled


def test_all_public_tables_have_rls_and_public_grants_are_repaired(intake_site):
    _, _, engine, _, _ = intake_site
    migration = import_module("migrations.versions.0010_durable_review_state")
    with engine.begin() as connection:
        connection.execute(text("GRANT SELECT ON public.users TO PUBLIC"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.protect()
        unprotected = (
            connection.execute(
                text("""SELECT relname FROM pg_class
            WHERE relnamespace='public'::regnamespace AND relkind='r' AND NOT relrowsecurity""")
            )
            .scalars()
            .all()
        )
        assert unprotected == []
        grants = (
            connection.execute(
                text("""SELECT c.relname FROM pg_class c,
            LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
            WHERE c.relnamespace='public'::regnamespace AND c.relkind='r'
            AND (a.grantee=0 OR a.grantee IN (SELECT oid FROM pg_roles
                WHERE rolname IN ('anon','authenticated','service_role')))""")
            )
            .scalars()
            .all()
        )
        assert grants == []
