"""Owner-bound snapshots, persisted jobs, rotation and content expiry cleanup."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.batches.contracts import BatchSettings
from app.cleanup.service import purge_unavailable_content
from app.db.batches import Batch, ScanJob
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, Workspace
from app.db.rotate_keys import rotate_batches
from tests.intake_support import _draft_body, _login


def make_batch(session, workspace, actor, keys, *, created=None, retention_days=7):
    protected = keys.encrypt_text("Synthetic private batch name")
    rules = keys.encrypt_text('[{"column":0,"header":"Synthetic header","mode":"scan"}]')
    batch = Batch(
        id=uuid4(),
        workspace_id=workspace,
        owner_id=actor,
        name_ciphertext=protected.ciphertext,
        name_key_id=protected.key_id,
        column_rules_ciphertext=rules.ciphertext,
        column_rules_key_id=rules.key_id,
        settings=BatchSettings(
            categories=["email"],
            phone_region="GB",
            language="en",
            retention_days=retention_days,
            preset_id=None,
            preset_version=None,
            preferred_action="label",
            category_defaults={},
        ).model_dump(mode="json"),
        uploaded_bytes=100,
        created_at=created or datetime.now(UTC),
    )
    session.add(batch)
    session.flush()
    return batch


def test_batch_snapshots_are_immutable_rotated_and_removed_after_final_child_content(intake_site):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post("/api/v1/documents", json=_draft_body(workspace), headers=headers)
    assert response.status_code == 201
    version = response.json()["version"]
    document_id = UUID(version["document_id"])
    keys = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session, session.begin():
        batch = make_batch(session, workspace, actor, keys)
        batch_id = batch.id
        document = session.get(Document, document_id)
        document.batch_id = batch.id
        document.batch_position = 1
        session.flush()
        session.add(
            ScanJob(
                document_id=document_id,
                batch_id=batch.id,
                source_revision_id=UUID(version["source_revision_id"]),
                settings_version=1,
            )
        )
    with Session(engine) as session:
        batch = session.get(Batch, batch_id)
        original = batch.name_ciphertext
        assert b"private" not in original and b"header" not in batch.column_rules_ciphertext
        batch.settings = {"categories": []}
        with pytest.raises(ValueError, match="immutable"):
            session.flush()
        session.rollback()
    with Session(engine) as session:
        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(text("UPDATE batches SET settings='{}' WHERE id=:id"), {"id": batch_id})
        session.rollback()
    new_value = Fernet.generate_key()
    rotated = KeyRing(
        "new",
        {
            "test": owner.app.state.settings.content_keys["test"].get_secret_value().encode(),
            "new": new_value,
        },
    )
    with Session(engine) as session, session.begin():
        session.info["allow_source_key_rotation"] = True
        session.execute(text("SET LOCAL openanonymi.key_rotation='on'"))
        assert rotate_batches(session, rotated) == 1
    only_new = KeyRing("new", {"new": new_value})
    with Session(engine) as session:
        batch = session.get(Batch, batch_id)
        assert (
            batch.name_ciphertext != original
            and batch.name_key_id == batch.column_rules_key_id == "new"
        )
        assert (
            only_new.decrypt_text(ProtectedValue(batch.name_ciphertext, batch.name_key_id))
            == "Synthetic private batch name"
        )
        assert "Synthetic header" in only_new.decrypt_text(
            ProtectedValue(batch.column_rules_ciphertext, batch.column_rules_key_id)
        )
        assert (
            session.scalar(select(ScanJob).where(ScanJob.document_id == document_id)).status
            == "queued"
        )
    now = datetime.now(UTC)
    assert purge_unavailable_content(engine, now=now).documents_purged == 0
    with Session(engine) as session, session.begin():
        document = session.get(Document, document_id)
        document.created_at = now - timedelta(days=2)
        document.expires_at = now - timedelta(seconds=1)
    assert purge_unavailable_content(engine, now=now).documents_purged == 1
    with Session(engine) as session:
        assert session.get(Batch, batch_id) is None
        assert (
            session.scalars(select(ScanJob).where(ScanJob.document_id == document_id)).all() == []
        )
        document = session.get(Document, document_id)
        assert (
            document.batch_id is None
            and document.batch_position is None
            and document.current_revision_id is None
        )


def test_empty_active_batch_lives_until_retention_and_deleted_empty_batch_is_removed(intake_site):
    owner, _, engine, workspace, actor = intake_site
    keys = KeyRing.from_settings(owner.app.state.settings)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        current = make_batch(session, workspace, actor, keys)
        old = make_batch(session, workspace, actor, keys, created=now - timedelta(days=8))
        deleted = make_batch(session, workspace, actor, keys, created=now - timedelta(days=1))
        deleted.deleted_at = now
        deleted.name_ciphertext = deleted.name_key_id = None
        deleted.column_rules_ciphertext = deleted.column_rules_key_id = None
        ids = (current.id, old.id, deleted.id)
    result = purge_unavailable_content(engine, now=now)
    assert result.expired_rows_removed == 2
    with Session(engine) as session:
        assert session.get(Batch, ids[0]) is not None
        assert session.get(Batch, ids[1]) is None and session.get(Batch, ids[2]) is None


@pytest.mark.parametrize(
    ("batch_days", "workspace_days", "age_days", "removed"),
    [(3, 7, 4, True), (7, 3, 4, True), (3, 7, 1, False)],
)
def test_empty_batch_uses_shorter_snapshot_or_current_workspace_retention(
    intake_site, batch_days, workspace_days, age_days, removed
):
    owner, _, engine, workspace, actor = intake_site
    keys = KeyRing.from_settings(owner.app.state.settings)
    now = datetime.now(UTC)
    headers = _login(owner, "intake-owner@example.invalid")
    with Session(engine) as session, session.begin():
        session.get(Workspace, workspace).content_retention_days = workspace_days
        batch = make_batch(
            session,
            workspace,
            actor,
            keys,
            created=now - timedelta(days=age_days),
            retention_days=batch_days,
        )
        batch_id = batch.id
    if age_days > batch_days:
        rejected = owner.post(
            f"/api/v1/batches/{batch_id}/documents",
            files={"file": ("fictional.txt", b"Fictional safe text", "text/plain")},
            headers=headers,
        )
        assert rejected.status_code == 410
        with Session(engine) as session:
            assert (
                session.scalars(select(Document.id).where(Document.batch_id == batch_id)).all()
                == []
            )
    result = purge_unavailable_content(engine, now=now)
    assert result.expired_rows_removed == int(removed)
    with Session(engine) as session:
        assert (session.get(Batch, batch_id) is None) == removed


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_owner",
        "missing_position",
        "position_outside_limit",
        "lease_without_owner",
        "wrong_revision",
        "wrong_batch",
    ],
)
def test_sql_batch_ownership_position_and_scan_lease_constraints(intake_site, mutation):
    owner, other, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    other_id = UUID(other.get("/api/v1/auth/session").json()["user_id"])
    response = owner.post("/api/v1/documents", json=_draft_body(workspace), headers=headers)
    version = response.json()["version"]
    keys = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session, session.begin():
        batch = make_batch(session, workspace, actor, keys)
        foreign = make_batch(session, workspace, other_id, keys)
        ids = {
            "batch": batch.id,
            "foreign": foreign.id,
            "document": UUID(version["document_id"]),
            "revision": UUID(version["source_revision_id"]),
            "job": uuid4(),
        }
        document = session.get(Document, ids["document"])
        document.batch_id = batch.id
        document.batch_position = 1
    with Session(engine) as session:
        with pytest.raises(DBAPIError):
            if mutation == "wrong_owner":
                session.execute(
                    text("UPDATE documents SET batch_id=:foreign WHERE id=:document"), ids
                )
            elif mutation == "missing_position":
                session.execute(
                    text("UPDATE documents SET batch_position=NULL WHERE id=:document"), ids
                )
            elif mutation == "position_outside_limit":
                session.execute(
                    text("UPDATE documents SET batch_position=21 WHERE id=:document"), ids
                )
            elif mutation == "lease_without_owner":
                session.execute(
                    text(
                        "INSERT INTO scan_jobs(id,document_id,source_revision_id,settings_version,status,lease_expires_at) VALUES (:job,:document,:revision,1,'leased',now())"
                    ),
                    ids,
                )
            elif mutation == "wrong_revision":
                session.execute(
                    text(
                        "INSERT INTO scan_jobs(id,document_id,source_revision_id,settings_version) VALUES (:job,:document,:job,1)"
                    ),
                    ids,
                )
            else:
                session.execute(
                    text(
                        "INSERT INTO scan_jobs(id,document_id,source_revision_id,settings_version,batch_id) VALUES (:job,:document,:revision,1,:foreign)"
                    ),
                    ids,
                )
        session.rollback()
