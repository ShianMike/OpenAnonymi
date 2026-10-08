"""Retiring grouping and queued work must leave individual reviews byte-for-byte intact."""

from importlib import import_module
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.models import AuditEvent, Document
from tests.test_source_csv_mutation_access_pg import mutation_case


def test_retirement_preserves_review_storage_and_removes_feature_routes(intake_site):
    case = mutation_case(intake_site, "noop-rules")
    owner, engine, base = case["client"], case["engine"], case["base"]
    preview = owner.get(base + "/preview").json()
    source = owner.get(base + "/source").json()
    migration = import_module("migrations.versions.0023_remove_batch_review")
    batch_id = uuid4()

    with engine.connect() as connection, connection.begin():

        def snapshot():
            return {
                name: sorted(connection.execute(table.select()).all(), key=repr)
                for name, table in Base.metadata.tables.items()
            }

        before = snapshot()
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            connection.execute(
                text("""INSERT INTO batches (id, workspace_id, owner_id, settings)
                    VALUES (:id, :workspace, :owner, '{}'::jsonb)"""),
                {"id": batch_id, "workspace": case["workspace"], "owner": case["actor"]},
            )
            connection.execute(
                text("UPDATE documents SET batch_id=:batch, batch_position=1 WHERE id=:id"),
                {"batch": batch_id, "id": case["document_id"]},
            )
            connection.execute(
                text("""INSERT INTO scan_jobs (id, document_id, batch_id, source_revision_id,
                    settings_version) SELECT :job, id, :batch, current_revision_id,
                    settings_version FROM documents WHERE id=:id"""),
                {"job": uuid4(), "batch": batch_id, "id": case["document_id"]},
            )
            for code in ("batch_created", "batch_deleted"):
                connection.execute(
                    AuditEvent.__table__.insert().values(
                        id=uuid4(),
                        workspace_id=case["workspace"],
                        actor_id=case["actor"],
                        event_code=code,
                        outcome="success",
                    )
                )
            migration.upgrade()
        assert snapshot() == before
        schema = inspect(connection)
        assert not {"batches", "scan_jobs"}.intersection(schema.get_table_names())
        assert not {"batch_id", "batch_position"}.intersection(
            column["name"] for column in schema.get_columns("documents")
        )
        assert connection.scalar(text("SELECT to_regprocedure('protect_batch_snapshot()')")) is None

    assert owner.get(base + "/source").json() == source
    assert owner.get(base + "/preview").json() == preview
    assert not {"batches", "scan_jobs"}.intersection(Base.metadata.tables)
    assert "batch_id" not in Document.__table__.columns
    assert all("/batches" not in path for path in owner.app.openapi()["paths"])
    for path in ("/api/v1/batches", f"/api/v1/batches/{batch_id}"):
        assert owner.get(path).status_code == 404
        assert owner.post(path, headers=case["headers"], json={}).status_code == 404
