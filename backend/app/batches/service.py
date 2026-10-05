"""Atomic batch intake; owner authorization precedes protected-content access."""

import json
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from phonenumbers import SUPPORTED_REGIONS
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import (
    ContentUnavailable,
    DocumentNotFound,
    active_workspace,
    owned_document,
    require_administrator,
)
from app.batches.contracts import (
    BatchDocumentView,
    BatchList,
    BatchListEntry,
    BatchSettings,
    BatchView,
    CreateBatchRequest,
    RuleRef,
)
from app.contracts import AUTOMATIC_CATEGORIES, DocumentStatus, WorkspaceRole
from app.db.batches import Batch, ScanJob
from app.db.column_rules import load_preset_rules
from app.db.crypto import KeyRing, ProtectedValue
from app.db.custom_rules import WorkspaceRule
from app.db.models import Document, Membership, Preset, User
from app.db.repository import (
    IntakeSnapshot,
    StorageValidationError,
    _version,
    create_document_in_transaction,
)
from app.detection.local_nlp import SUPPORTED_LANGUAGES
from app.intake.imports import ImportedText
from app.reviews.service import CompletionRejected, current_completion
from app.team_review.service import require_second_approval
from app.workspace.activity import record_event
from app.workspace.presets import PresetNotFound

MAX_BATCH_FILES = 20
MAX_BATCH_BYTES = 40 * 1024 * 1024


class BatchRejected(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class BatchReadChanged(RuntimeError):
    pass


def validate_batch_view(engine: Engine, actor_id: UUID, view: BatchView, now: datetime):
    """Refresh scalar access/expiry after serialization without decrypting again."""
    with Session(engine) as session:
        batch = owned_batch(session, view.id, actor_id)
        if batch.workspace_id != view.workspace_id:
            raise DocumentNotFound("Batch not found.")
        rows = session.scalars(select(Document).where(Document.batch_id == batch.id)).all()
        by_id = {row.id: row for row in rows}
        if set(by_id) != {item.id for item in view.documents}:
            raise BatchReadChanged("Batch changed while loading.")
        for item in view.documents:
            row = by_id[item.id]
            if row.owner_id != actor_id or row.workspace_id != batch.workspace_id:
                raise DocumentNotFound("Batch not found.")
            if (
                (_version(row) if row.current_revision_id else None) != item.version
                or row.expires_at != item.expires_at
                or (item.state not in ("expired", "deleted") and (
                    row.expires_at <= now or row.deleted_at is not None
                    or row.status in (DocumentStatus.EXPIRED, DocumentStatus.DELETED)
                ))
            ):
                raise BatchReadChanged("Batch changed while loading.")


def validate_batch_list(engine: Engine, workspace_id: UUID, actor_id: UUID, view: BatchList):
    with Session(engine) as session:
        active_workspace(session, workspace_id, actor_id)
        if view.workspace_total is not None:
            require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
        ids = {item.id for item in view.own_batches}
        available = set(session.scalars(select(Batch.id).where(
            Batch.id.in_(ids), Batch.workspace_id == workspace_id,
            Batch.owner_id == actor_id, Batch.deleted_at.is_(None),
        )))
        if available != ids:
            raise DocumentNotFound("Batch not found.")


def owned_batch(session: Session, batch_id: UUID, actor_id: UUID, *, lock=False) -> Batch:
    query = (
        select(Batch)
        .join(
            Membership,
            (Membership.workspace_id == Batch.workspace_id)
            & (Membership.user_id == Batch.owner_id),
        )
        .join(User, User.id == Batch.owner_id)
        .where(
            Batch.id == batch_id,
            Batch.owner_id == actor_id,
            Batch.deleted_at.is_(None),
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
        )
    )
    if lock:
        query = query.with_for_update(of=Batch)
    row = session.scalar(query)
    if row is None:
        raise DocumentNotFound("Batch not found.")
    return row


def create_batch(
    engine: Engine, actor_id: UUID, body: CreateBatchRequest, keys: KeyRing, now: datetime,
    reauthorize: Callable[[], object] | None = None,
) -> UUID:
    categories = set(body.categories)
    if not categories.issubset(AUTOMATIC_CATEGORIES):
        raise StorageValidationError("Choose supported detection categories.")
    if body.language not in SUPPORTED_LANGUAGES:
        raise StorageValidationError("Choose a supported language.")
    if body.phone_region.upper() not in SUPPORTED_REGIONS:
        raise StorageValidationError("Choose a supported phone region.")
    with Session(engine) as session, session.begin():
        workspace = active_workspace(session, body.workspace_id, actor_id)
        if reauthorize is not None:
            reauthorize()
            active_workspace(session, body.workspace_id, actor_id)
        retention = body.retention_days or workspace.content_retention_days
        if retention > workspace.content_retention_days:
            raise StorageValidationError("Expiry must be within the workspace retention period.")
        preset = None
        if body.preset_id:
            preset = session.scalar(
                select(Preset)
                .where(
                    Preset.id == body.preset_id,
                    Preset.workspace_id == workspace.id,
                )
                .with_for_update()
            )
            if preset is None:
                raise PresetNotFound("Preset not found.")
        column_rules = load_preset_rules(preset, keys) if preset else []
        protected_columns = keys.encrypt_text(json.dumps(column_rules)) if column_rules else None
        name = keys.encrypt_text(body.name) if body.name and body.name.strip() else None
        snapshot = BatchSettings(
            categories=preset.categories.split(",")
            if preset and preset.categories
            else []
            if preset
            else sorted(categories, key=lambda item: item.value),
            phone_region=preset.phone_region if preset else body.phone_region.upper(),
            language=body.language,
            preset_id=preset.id if preset else None,
            preset_version=preset.version if preset else None,
            preferred_action=preset.preferred_action if preset else "label",
            category_defaults=deepcopy(preset.category_defaults) if preset else {},
            retention_days=retention,
            custom_rules=[
                RuleRef(id=row.id, version=row.version)
                for row in session.scalars(
                    select(WorkspaceRule).where(
                        WorkspaceRule.workspace_id == workspace.id, WorkspaceRule.enabled.is_(True)
                    )
                )
            ],
        )
        batch = Batch(
            id=uuid4(),
            workspace_id=workspace.id,
            owner_id=actor_id,
            name_ciphertext=name.ciphertext if name else None,
            name_key_id=name.key_id if name else None,
            column_rules_ciphertext=protected_columns.ciphertext if protected_columns else None,
            column_rules_key_id=protected_columns.key_id if protected_columns else None,
            settings=snapshot.model_dump(mode="json"),
            uploaded_bytes=0,
            created_at=now,
        )
        session.add(batch)
        record_event(
            session,
            workspace_id=workspace.id,
            actor_id=actor_id,
            document_id=None,
            event_code="batch_created",
            now=now,
        )
        if reauthorize is not None:
            reauthorize()
            active_workspace(session, body.workspace_id, actor_id)
        session.flush()
        if reauthorize is not None:
            reauthorize()
            active_workspace(session, body.workspace_id, actor_id)
        return batch.id


def upload_document(
    engine: Engine,
    batch_id: UUID,
    actor_id: UUID,
    imported: ImportedText,
    raw_bytes: int,
    keys: KeyRing,
    now: datetime,
    reauthorize: Callable[[], object] | None = None,
):
    with Session(engine) as session, session.begin():
        batch = owned_batch(session, batch_id, actor_id, lock=True)
        if reauthorize is not None:
            reauthorize()
            owned_batch(session, batch_id, actor_id)
        settings = BatchSettings.model_validate(batch.settings)
        if batch.created_at + timedelta(days=settings.retention_days) <= (
            datetime.now(UTC) if reauthorize is not None else now
        ):
            raise ContentUnavailable("This batch no longer accepts uploads.")
        count = session.scalar(select(func.count(Document.id)).where(Document.batch_id == batch.id))
        if count >= MAX_BATCH_FILES:
            raise BatchRejected("batch_full", "A batch accepts at most 20 documents.")
        if batch.uploaded_bytes + raw_bytes > MAX_BATCH_BYTES:
            raise BatchRejected(
                "batch_too_large", "A batch accepts at most 40 MiB of uploaded files."
            )
        rules = load_preset_rules(batch, keys)
        saved = create_document_in_transaction(
            session,
            owner_id=actor_id,
            workspace_id=batch.workspace_id,
            source=imported.source.text,
            validated_source=imported.source,
            title=None,
            categories=set(settings.categories),
            phone_region=settings.phone_region,
            language=settings.language,
            keys=keys,
            now=now,
            requested_expiry=now + timedelta(days=settings.retention_days),
            layout=imported.layout,
            layout_kind=imported.format,
            snapshot=IntakeSnapshot(
                settings.preset_id,
                settings.preset_version,
                settings.preferred_action,
                settings.category_defaults,
                rules,
                tuple((rule.id, rule.version) for rule in settings.custom_rules),
            ),
        )
        document = session.get(Document, saved.version.document_id)
        document.batch_id, document.batch_position = batch.id, count + 1
        batch.uploaded_bytes += raw_bytes
        session.flush()
        session.add(
            ScanJob(
                document_id=document.id,
                batch_id=batch.id,
                source_revision_id=saved.version.source_revision_id,
                settings_version=1,
                status="queued",
                attempts=0,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        if reauthorize is not None:
            reauthorize()
            owned_batch(session, batch_id, actor_id)
            if batch.created_at + timedelta(days=settings.retention_days) <= datetime.now(UTC):
                raise ContentUnavailable("This batch no longer accepts uploads.")
            owned_document(session, document.id, actor_id, datetime.now(UTC))
        return saved


def _document_view(session: Session, document: Document, keys: KeyRing, now: datetime):
    state = "needs_review"
    version = _version(document) if document.current_revision_id else None
    job = session.scalar(
        select(ScanJob).where(
            ScanJob.document_id == document.id,
            ScanJob.source_revision_id == document.current_revision_id,
            ScanJob.settings_version == document.settings_version,
        )
    )
    if document.deleted_at is not None or document.status == DocumentStatus.DELETED:
        state = "deleted"
    elif document.expires_at <= now or document.status == DocumentStatus.EXPIRED:
        state = "expired"
    elif document.status in (DocumentStatus.READY, DocumentStatus.EXPORTED):
        try:
            current_completion(session, document)
            require_second_approval(session, document)
            from app.db.team_review import ReviewHandoff

            handoff = session.get(ReviewHandoff, document.id)
            state = (
                "exported"
                if document.status == DocumentStatus.EXPORTED
                else ("approved" if handoff and handoff.require_approval else "ready")
            )
        except CompletionRejected as exc:
            state = (
                "awaiting_approval" if exc.code == "second_approval_required" else "needs_review"
            )
    elif job and job.status == "queued":
        state = "queued"
    elif (job and job.status == "leased") or document.status == DocumentStatus.SCANNING:
        state = "scanning"
    elif (job and job.status == "failed") or document.status == DocumentStatus.FAILED:
        state = "scan_failed"
    title = None
    if state not in ("expired", "deleted") and document.title_ciphertext is not None:
        title = keys.decrypt_text(ProtectedValue(document.title_ciphertext, document.title_key_id))
    return BatchDocumentView(
        id=document.id,
        position=document.batch_position,
        title=title,
        state=state,
        version=version,
        expires_at=document.expires_at,
        last_error_code=job.last_error_code if job else None,
        attempts=job.attempts if job else 0,
    )


def load_batch(engine: Engine, batch_id: UUID, actor_id: UUID, keys: KeyRing, now: datetime):
    with Session(engine) as session:
        batch = owned_batch(session, batch_id, actor_id)
        name = (
            keys.decrypt_text(ProtectedValue(batch.name_ciphertext, batch.name_key_id))
            if batch.name_ciphertext is not None
            else None
        )
        documents = [
            _document_view(session, row, keys, now)
            for row in session.scalars(
                select(Document)
                .where(Document.batch_id == batch.id)
                .order_by(Document.batch_position)
            )
        ]
        return BatchView(
            id=batch.id,
            workspace_id=batch.workspace_id,
            name=name,
            settings=BatchSettings.model_validate(batch.settings),
            uploaded_bytes=batch.uploaded_bytes,
            created_at=batch.created_at,
            documents=documents,
            counts=dict(Counter(row.state for row in documents)),
            next_document_id=next(
                (row.id for row in documents if row.state == "needs_review"), None
            ),
            processing=any(row.state in ("queued", "scanning") for row in documents),
        )


def list_batches(engine: Engine, workspace_id: UUID, actor_id: UUID, keys: KeyRing):
    with Session(engine) as session:
        active_workspace(session, workspace_id, actor_id)
        rows = session.scalars(
            select(Batch)
            .where(
                Batch.owner_id == actor_id,
                Batch.workspace_id == workspace_id,
                Batch.deleted_at.is_(None),
            )
            .order_by(Batch.created_at.desc(), Batch.id.desc())
            .limit(100)
        ).all()
        membership = session.get(Membership, (workspace_id, actor_id))
        return BatchList(
            own_batches=[
                BatchListEntry(
                    id=row.id,
                    name=keys.decrypt_text(ProtectedValue(row.name_ciphertext, row.name_key_id))
                    if row.name_ciphertext is not None
                    else None,
                    created_at=row.created_at,
                    document_count=session.scalar(
                        select(func.count(Document.id)).where(Document.batch_id == row.id)
                    ),
                )
                for row in rows
            ],
            workspace_total=session.scalar(
                select(func.count(Batch.id)).where(
                    Batch.workspace_id == workspace_id,
                    Batch.deleted_at.is_(None),
                )
            )
            if membership.role == WorkspaceRole.ADMINISTRATOR
            else None,
        )


def retry_document(
    engine: Engine, batch_id: UUID, document_id: UUID, actor_id: UUID, now: datetime,
    reauthorize: Callable[[], object] | None = None,
):
    with Session(engine) as session, session.begin():
        owned_batch(session, batch_id, actor_id, lock=True)
        document = owned_document(session, document_id, actor_id, now, lock=True)
        if reauthorize is not None:
            reauthorize()
            owned_batch(session, batch_id, actor_id)
            owned_document(session, document_id, actor_id, datetime.now(UTC))
        if document.batch_id != batch_id:
            raise DocumentNotFound("Document not found.")
        job = session.scalar(
            select(ScanJob)
            .where(
                ScanJob.document_id == document.id,
                ScanJob.source_revision_id == document.current_revision_id,
                ScanJob.settings_version == document.settings_version,
            )
            .with_for_update()
        )
        if job is None or job.status != "failed":
            raise BatchRejected("scan_not_failed", "Only a failed queued scan can be retried.")
        job.status, job.attempts, job.last_error_code = "queued", 0, None
        job.available_at = job.updated_at = now
        session.flush()
        if reauthorize is not None:
            reauthorize()
            owned_batch(session, batch_id, actor_id)
            owned_document(session, document_id, actor_id, datetime.now(UTC))


def delete_batch(
    engine: Engine, batch_id: UUID, actor_id: UUID, now: datetime,
    reauthorize: Callable[[], object] | None = None,
) -> list[UUID]:
    with Session(engine) as session, session.begin():
        batch = owned_batch(session, batch_id, actor_id, lock=True)
        if reauthorize is not None:
            reauthorize()
            owned_batch(session, batch_id, actor_id)
        documents = session.scalars(
            select(Document)
            .where(
                Document.batch_id == batch.id,
            )
            .order_by(Document.id)
            .with_for_update()
        ).all()
        for document in documents:
            if document.deleted_at is None:
                document.deleted_at, document.updated_at = now, now
                document.status = DocumentStatus.DELETED
                document.title_ciphertext = document.title_key_id = None
                record_event(
                    session,
                    workspace_id=batch.workspace_id,
                    actor_id=actor_id,
                    document_id=document.id,
                    event_code="document_deleted",
                    now=now,
                )
        batch.deleted_at = now
        batch.name_ciphertext = batch.name_key_id = None
        batch.column_rules_ciphertext = batch.column_rules_key_id = None
        record_event(
            session,
            workspace_id=batch.workspace_id,
            actor_id=actor_id,
            document_id=None,
            event_code="batch_deleted",
            now=now,
        )
        session.flush()
        if reauthorize is not None:
            reauthorize()
            # The owned row is locked and was just tombstoned by this mutation.
            # Its membership must still be active before committing that deletion.
            active_workspace(session, batch.workspace_id, actor_id)
        return [row.id for row in documents]
