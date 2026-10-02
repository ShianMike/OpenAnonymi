"""Autosave is a protected working copy; it never changes confirmed review state."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.accounts.access import active_workspace, owned_document
from app.db.crypto import KeyRing, ProtectedValue
from app.db.recovery import RecoverySnapshot
from app.errors import ApiError
from app.recovery.contracts import RecoveryMetadata, RecoveryPayload, RecoveryView, RecoveryWrite

MAX_SNAPSHOTS = 20


def metadata(row: RecoverySnapshot) -> RecoveryMetadata:
    return RecoveryMetadata(
        id=row.id,
        workspace_id=row.workspace_id,
        document_id=row.document_id,
        version=row.version,
        updated_at=row.updated_at,
        expires_at=row.expires_at,
    )


def authorize_scope(
    session: Session,
    workspace_id: UUID,
    actor_id: UUID,
    document_id: UUID | None,
    now: datetime,
    *,
    lock: bool = False,
):
    workspace = active_workspace(session, workspace_id, actor_id)
    expiry = now + timedelta(days=workspace.content_retention_days)
    if document_id is not None:
        document = owned_document(session, document_id, actor_id, now, lock=lock)
        if document.workspace_id != workspace_id:
            raise ApiError(404, "document_not_found", "Document not found.")
        expiry = document.expires_at
    return expiry


def owned_snapshot(
    session: Session, workspace_id: UUID, snapshot_id: UUID, actor_id: UUID, now: datetime
) -> RecoverySnapshot:
    row = session.scalar(
        select(RecoverySnapshot)
        .where(
            RecoverySnapshot.id == snapshot_id,
            RecoverySnapshot.workspace_id == workspace_id,
            RecoverySnapshot.owner_id == actor_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(404, "recovery_not_found", "Working draft not found.")
    authorize_scope(session, workspace_id, actor_id, row.document_id, now)
    if row.expires_at <= now:
        raise ApiError(410, "recovery_expired", "This working draft has expired.")
    return row


def load_snapshot(
    session: Session,
    workspace_id: UUID,
    snapshot_id: UUID,
    actor_id: UUID,
    now: datetime,
    keys: KeyRing,
) -> RecoveryView:
    row = owned_snapshot(session, workspace_id, snapshot_id, actor_id, now)
    payload = RecoveryPayload.model_validate_json(
        keys.decrypt_text(ProtectedValue(row.payload_ciphertext, row.payload_key_id))
    )
    return RecoveryView(**metadata(row).model_dump(), payload=payload)


def save_snapshot(
    session: Session,
    workspace_id: UUID,
    snapshot_id: UUID,
    actor_id: UUID,
    body: RecoveryWrite,
    now: datetime,
    keys: KeyRing,
) -> RecoveryMetadata:
    # The workspace row serializes initial inserts and the per-owner bound. The
    # document lock also orders autosave against source commit/delete transactions.
    workspace = active_workspace(session, workspace_id, actor_id)
    session.refresh(workspace, with_for_update=True)
    expiry = authorize_scope(session, workspace_id, actor_id, body.document_id, now, lock=True)
    base = body.payload.base_version
    if (body.document_id is None and base is not None) or (
        body.document_id is not None and (base is None or base.document_id != body.document_id)
    ):
        raise ApiError(422, "invalid_recovery_scope", "Choose the working draft's document.")
    row = session.get(RecoverySnapshot, snapshot_id, with_for_update=True)
    if row is not None:
        if (
            row.owner_id != actor_id
            or row.workspace_id != workspace_id
            or row.document_id != body.document_id
        ):
            raise ApiError(404, "recovery_not_found", "Working draft not found.")
        if row.expires_at <= now:
            raise ApiError(410, "recovery_expired", "This working draft has expired.")
        if row.version != body.expected_version:
            raise ApiError(
                409,
                "recovery_conflict",
                "This working draft changed in another tab. Recover it before saving again.",
            )
    else:
        if body.expected_version != 0:
            raise ApiError(
                409,
                "recovery_conflict",
                "This working draft was removed. Recover or start a fresh working copy.",
            )
        session.execute(
            delete(RecoverySnapshot).where(
                RecoverySnapshot.owner_id == actor_id,
                RecoverySnapshot.expires_at <= now,
            )
        )
        existing = session.scalars(
            select(RecoverySnapshot.id)
            .where(
                RecoverySnapshot.owner_id == actor_id,
                RecoverySnapshot.workspace_id == workspace_id,
            )
            .limit(MAX_SNAPSHOTS)
        ).all()
        if len(existing) >= MAX_SNAPSHOTS:
            raise ApiError(
                409,
                "recovery_limit",
                "There are too many working drafts. Discard an older recovery copy first.",
            )
        row = RecoverySnapshot(
            id=snapshot_id,
            workspace_id=workspace_id,
            owner_id=actor_id,
            document_id=body.document_id,
            version=0,
            created_at=now,
            updated_at=now,
            expires_at=expiry,
        )
        session.add(row)
    protected = keys.encrypt_text(body.payload.model_dump_json())
    row.payload_ciphertext, row.payload_key_id = protected.ciphertext, protected.key_id
    row.version += 1
    row.updated_at = now
    row.expires_at = min(row.expires_at, expiry)
    session.flush()
    return metadata(row)
