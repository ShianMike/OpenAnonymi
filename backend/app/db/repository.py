"""Protected document storage. Public HTTP handlers will use these guarded operations."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.contracts import DocumentStatus, FindingCategory, SourceSpan, VersionRef
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, Finding, Membership, SourceRevision, User, Workspace
from app.intake.validation import validate_source
from app.lifecycle import require_transition


class DocumentNotFound(LookupError):
    """Also used for inaccessible documents, to avoid revealing their existence."""


class ContentUnavailable(RuntimeError):
    pass


class StorageValidationError(ValueError):
    pass


class VersionConflict(RuntimeError):
    def __init__(self, current: VersionRef):
        self.current = current
        super().__init__("This document changed in another session. Reload before saving.")


@dataclass(frozen=True)
class SavedDocument:
    version: VersionRef
    expires_at: datetime
    status: DocumentStatus


@dataclass(frozen=True)
class LoadedSource:
    version: VersionRef
    text: str
    expires_at: datetime
    status: DocumentStatus


def _version(document: Document) -> VersionRef:
    if document.current_revision_id is None:
        raise ContentUnavailable("The document has no saved source revision.")
    return VersionRef(
        document_id=document.id,
        source_revision_id=document.current_revision_id,
        decision_version=document.decision_version,
        settings_version=document.settings_version,
    )


def _owned_document(
    session: Session, document_id: UUID, actor_id: UUID, now: datetime, *, lock: bool = False
) -> Document:
    statement = (
        select(Document)
        .join(
            Membership,
            and_(
                Membership.workspace_id == Document.workspace_id,
                Membership.user_id == Document.owner_id,
            ),
        )
        .join(User, User.id == Membership.user_id)
        .where(
            Document.id == document_id,
            Document.owner_id == actor_id,
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
        )
    )
    if lock:
        statement = statement.with_for_update(of=Document)
    document = session.scalar(statement)
    if document is None:
        raise DocumentNotFound("Document not found.")
    if (
        document.deleted_at is not None
        or document.status
        in (
            DocumentStatus.EXPIRED,
            DocumentStatus.DELETED,
        )
        or document.expires_at <= now
    ):
        raise ContentUnavailable("This document has expired or was deleted.")
    return document


def _active_workspace(session: Session, workspace_id: UUID, owner_id: UUID) -> Workspace:
    workspace = session.scalar(
        select(Workspace)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Workspace.id == workspace_id,
            Membership.user_id == owner_id,
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
        )
    )
    if workspace is None:
        raise DocumentNotFound("Workspace not found.")
    return workspace


def create_document(
    session: Session,
    *,
    owner_id: UUID,
    workspace_id: UUID,
    source: str,
    title: str | None,
    categories: set[FindingCategory],
    phone_region: str,
    keys: KeyRing,
    now: datetime,
    requested_expiry: datetime | None = None,
) -> SavedDocument:
    validated = validate_source(source)
    if now.tzinfo is None:
        raise StorageValidationError("A timezone-aware time is required.")
    if requested_expiry is not None and requested_expiry.tzinfo is None:
        raise StorageValidationError("A timezone-aware expiry is required.")
    if title is not None and len(title) > 200:
        raise StorageValidationError("Title must be 200 characters or fewer.")
    if not phone_region.isascii() or len(phone_region) != 2 or not phone_region.isalpha():
        raise StorageValidationError("Choose a two-letter phone region.")
    if not categories.issubset(set(FindingCategory)):
        raise StorageValidationError("Choose supported detection categories.")

    with session.begin():
        workspace = _active_workspace(session, workspace_id, owner_id)
        max_expiry = now + timedelta(days=workspace.content_retention_days)
        expiry = requested_expiry or max_expiry
        if expiry <= now or expiry > max_expiry:
            raise StorageValidationError("Expiry must be within the workspace retention period.")
        protected_source = keys.encrypt_text(validated.text)
        protected_title = keys.encrypt_text(title) if title and title.strip() else None
        document = Document(
            id=uuid4(),
            workspace_id=workspace_id,
            owner_id=owner_id,
            title_ciphertext=protected_title.ciphertext if protected_title else None,
            title_key_id=protected_title.key_id if protected_title else None,
            status=DocumentStatus.DRAFT,
            decision_version=0,
            settings_version=1,
            category_settings=",".join(sorted(category.value for category in categories)),
            phone_region=phone_region.upper(),
            created_at=now,
            updated_at=now,
            expires_at=expiry,
        )
        session.add(document)
        session.flush()
        revision = SourceRevision(
            id=uuid4(),
            document_id=document.id,
            revision_number=1,
            source_ciphertext=protected_source.ciphertext,
            source_key_id=protected_source.key_id,
            utf8_bytes=validated.utf8_bytes,
            code_points=validated.code_points,
            created_at=now,
        )
        session.add(revision)
        session.flush()
        document.current_revision_id = revision.id
        session.flush()
        saved = SavedDocument(_version(document), expiry, DocumentStatus.DRAFT)
    return saved


def load_current_source(
    session: Session, *, document_id: UUID, actor_id: UUID, keys: KeyRing, now: datetime
) -> LoadedSource:
    document = _owned_document(session, document_id, actor_id, now)
    version = _version(document)
    revision = session.scalar(
        select(SourceRevision).where(
            SourceRevision.document_id == document_id,
            SourceRevision.id == version.source_revision_id,
        )
    )
    if revision is None:
        raise ContentUnavailable("The current source revision is unavailable.")
    text = keys.decrypt_text(ProtectedValue(revision.source_ciphertext, revision.source_key_id))
    return LoadedSource(version, text, document.expires_at, DocumentStatus(document.status))


def append_source_revision(
    session: Session,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    source: str,
    keys: KeyRing,
    now: datetime,
) -> SavedDocument:
    validated = validate_source(source)
    with session.begin():
        document = _owned_document(session, document_id, actor_id, now, lock=True)
        current = _version(document)
        if expected != current:
            raise VersionConflict(current)
        previous_number = session.scalar(
            select(func.max(SourceRevision.revision_number)).where(
                SourceRevision.document_id == document_id
            )
        )
        protected = keys.encrypt_text(validated.text)
        revision = SourceRevision(
            id=uuid4(),
            document_id=document_id,
            revision_number=(previous_number or 0) + 1,
            source_ciphertext=protected.ciphertext,
            source_key_id=protected.key_id,
            utf8_bytes=validated.utf8_bytes,
            code_points=validated.code_points,
            created_at=now,
        )
        session.add(revision)
        session.flush()
        document.current_revision_id = revision.id
        document.decision_version += 1
        if document.status != DocumentStatus.DRAFT:
            require_transition(DocumentStatus(document.status), DocumentStatus.DRAFT)
        document.status = DocumentStatus.DRAFT
        document.updated_at = now
        session.flush()
        saved = SavedDocument(_version(document), document.expires_at, DocumentStatus.DRAFT)
    return saved


def add_manual_finding(
    session: Session,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    span: SourceSpan,
    category: FindingCategory,
    now: datetime,
) -> UUID:
    with session.begin():
        document = _owned_document(session, document_id, actor_id, now, lock=True)
        current = _version(document)
        if expected != current:
            raise VersionConflict(current)
        revision = session.get(SourceRevision, current.source_revision_id)
        if (
            revision is None
            or revision.document_id != document_id
            or span.end > revision.code_points
        ):
            raise StorageValidationError("The selected range is outside the current source.")
        finding = Finding(
            id=uuid4(),
            document_id=document_id,
            source_revision_id=revision.id,
            category=category.value,
            origin="manual",
            start_offset=span.start,
            end_offset=span.end,
            created_at=now,
        )
        session.add(finding)
        document.decision_version += 1
        if document.status != DocumentStatus.NEEDS_REVIEW:
            require_transition(DocumentStatus(document.status), DocumentStatus.NEEDS_REVIEW)
        document.status = DocumentStatus.NEEDS_REVIEW
        document.updated_at = now
        session.flush()
        finding_id = finding.id
    return finding_id
