"""Every app and migration table denies inherited public API grants."""

from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


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
