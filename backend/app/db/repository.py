"""Protected document storage. Public HTTP handlers will use these guarded operations."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from phonenumbers import SUPPORTED_REGIONS
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.access import (
    ContentUnavailable,
    DocumentNotFound,
    WorkspaceAccessDenied,
    active_workspace,
    owned_document,
    review_document,
)
from app.contracts import (
    AUTOMATIC_CATEGORIES,
    DocumentStatus,
    FindingCategory,
    SourceSpan,
    VersionRef,
)
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, Finding, Preset, SourceRevision
from app.intake.validation import validate_source
from app.lifecycle import require_transition
from app.workspace.activity import record_event
from app.workspace.presets import PresetNotFound


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
    structure: str = "none"


@dataclass(frozen=True)
class LoadedSource:
    workspace_id: UUID
    can_edit: bool
    version: VersionRef
    text: str
    expires_at: datetime
    status: DocumentStatus
    title: str | None
    categories: tuple[FindingCategory, ...]
    phone_region: str
    preset_id: UUID | None
    preset_version: int | None
    preferred_action: str
    language: str
    category_defaults: dict
    structure: str


def _version(document: Document) -> VersionRef:
    if document.current_revision_id is None:
        raise ContentUnavailable("The document has no saved source revision.")
    return VersionRef(
        document_id=document.id,
        source_revision_id=document.current_revision_id,
        decision_version=document.decision_version,
        settings_version=document.settings_version,
    )


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
    preset_id: UUID | None = None,
    language: str = "en",
    layout: dict | None = None,
) -> SavedDocument:
    from app.detection.local_nlp import SUPPORTED_LANGUAGES

    if language not in SUPPORTED_LANGUAGES:
        raise StorageValidationError("Choose a supported language.")
    validated = validate_source(source)
    if now.tzinfo is None:
        raise StorageValidationError("A timezone-aware time is required.")
    if requested_expiry is not None and requested_expiry.tzinfo is None:
        raise StorageValidationError("A timezone-aware expiry is required.")
    if title is not None and len(title) > 200:
        raise StorageValidationError("Title must be 200 characters or fewer.")
    if phone_region.upper() not in SUPPORTED_REGIONS:
        raise StorageValidationError("Choose a supported phone region.")
    if not categories.issubset(AUTOMATIC_CATEGORIES):
        raise StorageValidationError("Choose supported detection categories.")

    with session.begin():
        try:
            workspace = active_workspace(session, workspace_id, owner_id)
        except WorkspaceAccessDenied:
            raise DocumentNotFound("Workspace not found.") from None
        selected_preset = None
        if preset_id is not None:
            selected_preset = session.scalar(
                select(Preset).where(Preset.id == preset_id, Preset.workspace_id == workspace_id)
            )
            if selected_preset is None:
                raise PresetNotFound("Preset not found.")
            categories = {
                FindingCategory(value) for value in selected_preset.categories.split(",") if value
            }
            phone_region = selected_preset.phone_region
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
            language=language,
            preset_id=selected_preset.id if selected_preset else None,
            preset_version=selected_preset.version if selected_preset else None,
            preferred_action=selected_preset.preferred_action if selected_preset else "label",
            category_defaults=deepcopy(selected_preset.category_defaults)
            if selected_preset
            else {},
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
        from app.db.source_structures import store_word

        store_word(session, revision.id, layout, validated.text, keys, now)
        document.current_revision_id = revision.id
        from app.custom_rules.service import snapshot_rules

        snapshot_rules(session, document)
        session.flush()
        record_event(
            session,
            workspace_id=workspace_id,
            actor_id=owner_id,
            document_id=document.id,
            event_code="document_created",
            now=now,
        )
        saved = SavedDocument(
            _version(document), expiry, DocumentStatus.DRAFT, "kept" if layout else "none"
        )
    return saved


def load_current_source(
    session: Session, *, document_id: UUID, actor_id: UUID, keys: KeyRing, now: datetime
) -> LoadedSource:
    document = review_document(session, document_id, actor_id, now)
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
    title = (
        keys.decrypt_text(ProtectedValue(document.title_ciphertext, document.title_key_id))
        if document.title_ciphertext is not None and document.title_key_id is not None
        else None
    )
    categories = tuple(
        FindingCategory(value) for value in document.category_settings.split(",") if value
    )
    from app.db.source_structures import SourceStructure

    structure = "kept" if session.get(SourceStructure, revision.id) else "none"
    return LoadedSource(
        document.workspace_id,
        document.owner_id == actor_id,
        version,
        text,
        document.expires_at,
        DocumentStatus(document.status),
        title,
        categories,
        document.phone_region,
        document.preset_id,
        document.preset_version,
        document.preferred_action,
        document.language,
        deepcopy(document.category_defaults),
        structure,
    )


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
        document = owned_document(session, document_id, actor_id, now, lock=True)
        current = _version(document)
        if expected != current:
            raise VersionConflict(current)
        from app.db.source_structures import SourceStructure, load_word, store_word
        from app.intake.structure import realign_word

        old_layout, new_layout = None, None
        if session.get(SourceStructure, current.source_revision_id) is not None:
            old_revision = session.get(SourceRevision, current.source_revision_id)
            old_text = keys.decrypt_text(
                ProtectedValue(old_revision.source_ciphertext, old_revision.source_key_id)
            )
            old_layout = load_word(
                session, current.source_revision_id, keys, len(old_text), old_text
            )
            new_layout = realign_word(old_layout, old_text, validated.text)
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
        store_word(session, revision.id, new_layout, validated.text, keys, now)
        document.current_revision_id = revision.id
        from app.groups.undo_store import clear_document

        clear_document(session, document.id)
        document.decision_version += 1
        if document.status != DocumentStatus.DRAFT:
            require_transition(DocumentStatus(document.status), DocumentStatus.DRAFT)
        document.status = DocumentStatus.DRAFT
        document.updated_at = now
        session.flush()
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document.id,
            event_code="source_revised",
            now=now,
        )
        saved = SavedDocument(
            _version(document),
            document.expires_at,
            DocumentStatus.DRAFT,
            "kept" if new_layout else "simplified" if old_layout else "none",
        )
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
        document = owned_document(session, document_id, actor_id, now, lock=True)
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
