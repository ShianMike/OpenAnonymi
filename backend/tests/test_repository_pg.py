"""Focused storage gate. Run only against an explicitly selected local test database."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.contracts import DocumentStatus, FindingCategory, SourceSpan
from app.db.crypto import KeyRing, ProtectedValue
from app.db.labels import create_labeled_group
from app.db.models import (
    Document,
    EntityGroup,
    Finding,
    ImmutableSourceRevision,
    Membership,
    SourceRevision,
    User,
    Workspace,
)
from app.db.repository import (
    ContentUnavailable,
    DocumentNotFound,
    VersionConflict,
    add_manual_finding,
    append_source_revision,
    create_document,
    load_current_source,
)
from app.db.rotate_keys import rotate_database


@pytest.fixture
def local_database():
    raw_url = os.getenv("PRIVACY_REVIEW_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("set PRIVACY_REVIEW_TEST_DATABASE_URL for the local database gate")
    url = make_url(raw_url)
    if url.host not in ("127.0.0.1", "localhost") or url.port not in (5433, 5434):
        pytest.fail("repository test requires a local database on port 5433 or 5434")
    engine = create_engine(raw_url, pool_pre_ping=True, hide_parameters=True)
    user_id, admin_id, workspace_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                User(
                    id=user_id, email=f"owner-{user_id}@example.invalid", password_hash="test-only"
                ),
                User(
                    id=admin_id,
                    email=f"admin-{admin_id}@example.invalid",
                    password_hash="test-only",
                ),
                Workspace(id=workspace_id, name="Synthetic workspace", content_retention_days=7),
            ]
        )
        session.flush()
        session.add_all(
            [
                Membership(workspace_id=workspace_id, user_id=user_id, role="member"),
                Membership(workspace_id=workspace_id, user_id=admin_id, role="administrator"),
            ]
        )
    try:
        yield engine, user_id, admin_id, workspace_id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Document).where(Document.workspace_id == workspace_id))
            session.execute(delete(Membership).where(Membership.workspace_id == workspace_id))
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id.in_([user_id, admin_id])))
        engine.dispose()


def test_encrypted_revision_persists_and_admin_cannot_read_owner_content(local_database):
    engine, user_id, admin_id, workspace_id = local_database
    now = datetime.now(UTC)
    keys = KeyRing("test-v1", {"test-v1": Fernet.generate_key()})
    source = "Synthetic client 😀\r\nSynthetic client"
    with Session(engine) as session:
        saved = create_document(
            session,
            owner_id=user_id,
            workspace_id=workspace_id,
            source=source,
            title="Synthetic title",
            categories={FindingCategory.EMAIL, FindingCategory.PHONE},
            phone_region="PH",
            keys=keys,
            now=now,
        )

    # A new session reloads the persisted source; the database column contains ciphertext.
    with Session(engine) as session:
        loaded = load_current_source(
            session, document_id=saved.version.document_id, actor_id=user_id, keys=keys, now=now
        )
        assert loaded.text == source
        assert loaded.version == saved.version
        revision = session.get(SourceRevision, saved.version.source_revision_id)
        assert revision is not None
        assert source.encode("utf-8") not in revision.source_ciphertext
        assert revision.source_key_id == "test-v1"
        document = session.get(Document, saved.version.document_id)
        assert document.title_ciphertext is not None
        assert b"Synthetic title" not in document.title_ciphertext
        with pytest.raises(DocumentNotFound):
            load_current_source(
                session,
                document_id=saved.version.document_id,
                actor_id=admin_id,
                keys=keys,
                now=now,
            )

    with Session(engine) as session:
        finding_id = add_manual_finding(
            session,
            document_id=saved.version.document_id,
            actor_id=user_id,
            expected=saved.version,
            span=SourceSpan(start=0, end=9),
            category=FindingCategory.PERSON,
            now=now,
        )
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        assert finding.source_revision_id == saved.version.source_revision_id
        current = load_current_source(
            session, document_id=saved.version.document_id, actor_id=user_id, keys=keys, now=now
        )
        assert current.version.decision_version == saved.version.decision_version + 1
        assert current.status == DocumentStatus.NEEDS_REVIEW

    with Session(engine) as session:
        group = create_labeled_group(
            session,
            document_id=saved.version.document_id,
            actor_id=user_id,
            expected=current.version,
            category=FindingCategory.PERSON,
            now=now,
        )
        assert group.label == "PERSON_001"
    with Session(engine) as session:
        current = load_current_source(
            session, document_id=saved.version.document_id, actor_id=user_id, keys=keys, now=now
        )
    with Session(engine) as session:
        group = create_labeled_group(
            session,
            document_id=saved.version.document_id,
            actor_id=user_id,
            expected=current.version,
            category=FindingCategory.PERSON,
            now=now,
        )
        assert group.label == "PERSON_002"
    with Session(engine) as session:
        current = load_current_source(
            session, document_id=saved.version.document_id, actor_id=user_id, keys=keys, now=now
        )

    changed = source + "\r\nAnother line"
    with Session(engine) as session:
        revised = append_source_revision(
            session,
            document_id=saved.version.document_id,
            actor_id=user_id,
            expected=current.version,
            source=changed,
            keys=keys,
            now=now + timedelta(minutes=1),
        )
    assert revised.version.source_revision_id != saved.version.source_revision_id
    with Session(engine) as session:
        revisions = session.scalars(
            select(SourceRevision).where(SourceRevision.document_id == saved.version.document_id)
        ).all()
        assert len(revisions) == 2
        assert [revision.revision_number for revision in revisions] == [1, 2]
        assert (
            load_current_source(
                session,
                document_id=saved.version.document_id,
                actor_id=user_id,
                keys=keys,
                now=now + timedelta(minutes=1),
            ).text
            == changed
        )
        with pytest.raises(ContentUnavailable):
            load_current_source(
                session,
                document_id=saved.version.document_id,
                actor_id=user_id,
                keys=keys,
                now=saved.expires_at,
            )
    with Session(engine) as session:
        old_revision = session.get(SourceRevision, saved.version.source_revision_id)
        old_revision.revision_number = 99
        with pytest.raises(ImmutableSourceRevision):
            session.flush()
        session.rollback()
    with Session(engine) as session:
        old_revision = session.get(SourceRevision, saved.version.source_revision_id)
        session.info["allow_source_key_rotation"] = True
        old_revision.revision_number = 99
        with pytest.raises(ImmutableSourceRevision):
            session.flush()
        session.rollback()
    with Session(engine) as session:
        assert session.get(SourceRevision, saved.version.source_revision_id).revision_number == 1
    with Session(engine) as session, pytest.raises(VersionConflict):
        append_source_revision(
            session,
            document_id=saved.version.document_id,
            actor_id=user_id,
            expected=saved.version,
            source="Stale change",
            keys=keys,
            now=now + timedelta(minutes=2),
        )


def test_database_key_rotation_preserves_content(local_database, monkeypatch):
    engine, user_id, _admin_id, workspace_id = local_database
    now = datetime.now(UTC)
    first, second = Fernet.generate_key(), Fernet.generate_key()
    old_keys = KeyRing("old", {"old": first})
    with Session(engine) as session:
        saved = create_document(
            session,
            owner_id=user_id,
            workspace_id=workspace_id,
            source="Synthetic protected source",
            title="Synthetic protected title",
            categories=set(),
            phone_region="PH",
            keys=old_keys,
            now=now,
        )
    monkeypatch.setenv(
        "PRIVACY_REVIEW_DATABASE_URL", engine.url.render_as_string(hide_password=False)
    )
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("PRIVACY_REVIEW_ENVIRONMENT", "test")
    monkeypatch.setenv("PRIVACY_REVIEW_ACTIVE_KEY_ID", "new")
    monkeypatch.setenv(
        "PRIVACY_REVIEW_CONTENT_KEYS",
        json.dumps({"old": first.decode(), "new": second.decode()}),
    )
    from app.config import load_settings

    # The local PGlite socket has a single underlying connection. Release the
    # fixture engine's pool before the operational command opens its own engine.
    engine.dispose()
    totals = rotate_database(load_settings(), KeyRing("new", {"old": first, "new": second}))
    assert totals["titles"] >= 1
    assert totals["source revisions"] >= 1
    new_only = KeyRing("new", {"new": second})
    with Session(engine) as session:
        loaded = load_current_source(
            session,
            document_id=saved.version.document_id,
            actor_id=user_id,
            keys=new_only,
            now=now,
        )
        assert loaded.text == "Synthetic protected source"
        document = session.get(Document, saved.version.document_id)
        assert document.title_key_id == "new"
        assert (
            new_only.decrypt_text(ProtectedValue(document.title_ciphertext, document.title_key_id))
            == "Synthetic protected title"
        )


def test_real_postgres_serializes_label_allocation_and_guards_raw_source_updates(local_database):
    engine, user_id, _admin_id, workspace_id = local_database
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version()"))
        if "PGlite" in version.scalar():
            pytest.skip("PGlite's connection multiplexer cannot prove PostgreSQL concurrency")
    now = datetime.now(UTC)
    keys = KeyRing("test", {"test": Fernet.generate_key()})
    with Session(engine) as session:
        saved = create_document(
            session,
            owner_id=user_id,
            workspace_id=workspace_id,
            source="Synthetic repeated person",
            title=None,
            categories=set(),
            phone_region="PH",
            keys=keys,
            now=now,
        )

    barrier = Barrier(2)

    def allocate():
        barrier.wait(timeout=5)
        with Session(engine) as session:
            return create_labeled_group(
                session,
                document_id=saved.version.document_id,
                actor_id=user_id,
                expected=saved.version,
                category=FindingCategory.PERSON,
                now=now,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(allocate) for _ in range(2)]
        results = []
        for future in futures:
            try:
                results.append(future.result(timeout=10))
            except VersionConflict:
                results.append("conflict")
    assert sorted(
        result.label if isinstance(result, EntityGroup) else result for result in results
    ) == [
        "PERSON_001",
        "conflict",
    ]
    with Session(engine) as session:
        groups = session.scalars(
            select(EntityGroup).where(EntityGroup.document_id == saved.version.document_id)
        ).all()
        assert len(groups) == 1

    with Session(engine) as session:
        with pytest.raises(DBAPIError):
            session.execute(
                update(SourceRevision)
                .where(SourceRevision.id == saved.version.source_revision_id)
                .values(revision_number=99)
            )
            session.commit()
        session.rollback()
    with Session(engine) as session:
        assert session.get(SourceRevision, saved.version.source_revision_id).revision_number == 1
