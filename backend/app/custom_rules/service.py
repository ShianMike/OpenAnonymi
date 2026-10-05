"""Authorized rule storage with document-specific settings snapshots."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.access import (
    active_workspace,
    owned_document,
    refresh_document_access,
    refresh_workspace_access,
    require_administrator,
)
from app.contracts import DocumentStatus
from app.custom_rules.contracts import RuleInput, RuleSnapshotView, RuleView
from app.db.crypto import KeyRing, ProtectedValue
from app.db.custom_rules import DocumentRuleSnapshot, RuleVersion, WorkspaceRule
from app.db.models import Document
from app.db.repository import VersionConflict, _version
from app.errors import ApiError
from app.lifecycle import require_transition
from app.workspace.activity import record_event

MAX_RULES = 50


class RuleNotFound(LookupError):
    pass


class RuleConflict(RuntimeError):
    pass


def rule_view(row: WorkspaceRule, version: RuleVersion, keys: KeyRing) -> RuleView:
    payload = RuleInput.model_validate_json(
        keys.decrypt_text(ProtectedValue(version.payload_ciphertext, version.payload_key_id))
    )
    return RuleView(
        **payload.model_dump(), id=row.id, version=version.version, updated_at=version.created_at
    )


def workspace_rules(session: Session, workspace_id: UUID, keys: KeyRing) -> list[RuleView]:
    rows = session.execute(
        select(WorkspaceRule, RuleVersion)
        .join(
            RuleVersion,
            (RuleVersion.rule_id == WorkspaceRule.id)
            & (RuleVersion.version == WorkspaceRule.version),
        )
        .where(WorkspaceRule.workspace_id == workspace_id)
        .order_by(WorkspaceRule.created_at)
    ).all()
    return [rule_view(row, version, keys) for row, version in rows]


def save_rule(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    keys: KeyRing,
    now: datetime,
    body: RuleInput,
    rule_id: UUID | None = None,
    expected_version: int | None = None,
    reauthorize: Callable[[], object] | None = None,
) -> RuleView:
    with session.begin():
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id, lock=True)
        refresh_workspace_access(session, workspace_id, actor_id, reauthorize, administrator=True)
        row = session.get(WorkspaceRule, rule_id) if rule_id else None
        if rule_id and (row is None or row.workspace_id != workspace_id):
            raise RuleNotFound()
        if row:
            if row.version != expected_version:
                raise RuleConflict()
            row.version += 1
            row.enabled = body.enabled
            row.updated_at = now
        else:
            if (
                len(
                    session.scalars(
                        select(WorkspaceRule.id).where(WorkspaceRule.workspace_id == workspace_id)
                    ).all()
                )
                >= MAX_RULES
            ):
                raise ValueError(
                    "This workspace has reached its 50-rule limit. Edit an existing rule."
                )
            row = WorkspaceRule(
                id=uuid4(),
                workspace_id=workspace_id,
                version=1,
                enabled=body.enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
        protected = keys.encrypt_text(body.model_dump_json())
        version = RuleVersion(
            rule_id=row.id,
            version=row.version,
            payload_ciphertext=protected.ciphertext,
            payload_key_id=protected.key_id,
            created_at=now,
        )
        session.add(version)
        session.flush()
        record_event(
            session,
            workspace_id=workspace_id,
            actor_id=actor_id,
            document_id=None,
            event_code="workspace_rule_saved",
            now=now,
        )
        result = rule_view(row, version, keys)
        session.flush()
        refresh_workspace_access(session, workspace_id, actor_id, reauthorize, administrator=True)
        return result


def snapshot_rules(session: Session, document: Document):
    for row in session.scalars(
        select(WorkspaceRule).where(
            WorkspaceRule.workspace_id == document.workspace_id, WorkspaceRule.enabled.is_(True)
        )
    ):
        session.add(
            DocumentRuleSnapshot(
                document_id=document.id,
                settings_version=document.settings_version,
                rule_id=row.id,
                rule_version=row.version,
            )
        )


def copy_snapshot(session: Session, document: Document, previous_settings: int):
    for row in session.scalars(
        select(DocumentRuleSnapshot).where(
            DocumentRuleSnapshot.document_id == document.id,
            DocumentRuleSnapshot.settings_version == previous_settings,
        )
    ):
        session.add(
            DocumentRuleSnapshot(
                document_id=document.id,
                settings_version=document.settings_version,
                rule_id=row.rule_id,
                rule_version=row.rule_version,
            )
        )


def load_snapshot(session: Session, document: Document, keys: KeyRing) -> list[RuleView]:
    rows = session.execute(
        select(WorkspaceRule, RuleVersion)
        .join(RuleVersion, RuleVersion.rule_id == WorkspaceRule.id)
        .join(
            DocumentRuleSnapshot,
            (DocumentRuleSnapshot.rule_id == RuleVersion.rule_id)
            & (DocumentRuleSnapshot.rule_version == RuleVersion.version),
        )
        .where(
            DocumentRuleSnapshot.document_id == document.id,
            DocumentRuleSnapshot.settings_version == document.settings_version,
        )
        .order_by(WorkspaceRule.created_at)
    ).all()
    return [rule_view(row, version, keys) for row, version in rows]


def snapshot_state(session: Session, document: Document, keys: KeyRing) -> RuleSnapshotView:
    saved = load_snapshot(session, document, keys)
    latest = [
        rule for rule in workspace_rules(session, document.workspace_id, keys) if rule.enabled
    ]
    signature = lambda items: sorted((str(item.id), item.version) for item in items)
    return RuleSnapshotView(
        version=_version(document),
        rules=saved,
        update_available=signature(saved) != signature(latest),
    )


def refresh_snapshot(
    session: Session,
    document_id: UUID,
    actor_id: UUID,
    expected,
    now: datetime,
    keys: KeyRing,
    *,
    reauthorize: Callable[[], object] | None = None,
) -> RuleSnapshotView:
    with session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        refresh_document_access(session, document_id, actor_id, reauthorize, owner=True)
        active_workspace(session, document.workspace_id, actor_id)
        if _version(document) != expected:
            raise VersionConflict(_version(document))
        if not snapshot_state(session, document, keys).update_available:
            result = snapshot_state(session, document, keys)
            refresh_document_access(session, document_id, actor_id, reauthorize, owner=True)
            return result
        document.settings_version += 1
        from app.groups.undo_store import clear_document

        clear_document(session, document.id)
        document.decision_version += 1
        if document.status != DocumentStatus.DRAFT:
            require_transition(DocumentStatus(document.status), DocumentStatus.DRAFT)
        document.status = DocumentStatus.DRAFT
        document.updated_at = now
        snapshot_rules(session, document)
        session.flush()
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document.id,
            event_code="scan_settings_changed",
            now=now,
        )
        result = snapshot_state(session, document, keys)
        session.flush()
        refresh_document_access(session, document_id, actor_id, reauthorize, owner=True)
        return result


def validate_rule_view(session, workspace_id, actor_id, view):
    """Check current membership and versions after private rule serialization."""
    active_workspace(session, workspace_id, actor_id)
    items = view if isinstance(view, list) else [view]
    statement = select(WorkspaceRule.id, WorkspaceRule.version).where(
        WorkspaceRule.workspace_id == workspace_id
    )
    if not isinstance(view, list):
        statement = statement.where(WorkspaceRule.id == view.id)
    current = set(session.execute(statement).all())
    if current != {(item.id, item.version) for item in items}:
        raise ApiError(409, "rules_changed", "Rules changed. Reload before continuing.")
    active_workspace(session, workspace_id, actor_id)


def validate_snapshot_view(session, document_id, actor_id, view):
    """A saved document snapshot remains readable only with its current version."""
    document = owned_document(session, document_id, actor_id, datetime.now(UTC))
    active_workspace(session, document.workspace_id, actor_id)
    saved = set(
        session.execute(
            select(
                DocumentRuleSnapshot.rule_id,
                DocumentRuleSnapshot.rule_version,
            ).where(
                DocumentRuleSnapshot.document_id == document_id,
                DocumentRuleSnapshot.settings_version == document.settings_version,
            )
        ).all()
    )
    latest = set(
        session.execute(
            select(WorkspaceRule.id, WorkspaceRule.version).where(
                WorkspaceRule.workspace_id == document.workspace_id,
                WorkspaceRule.enabled.is_(True),
            )
        ).all()
    )
    session.expire(document)
    document = owned_document(session, document_id, actor_id, datetime.now(UTC))
    active_workspace(session, document.workspace_id, actor_id)
    if (
        _version(document) != view.version
        or saved != {(rule.id, rule.version) for rule in view.rules}
        or (saved != latest) != view.update_available
    ):
        raise ApiError(409, "rules_changed", "Review rules changed. Reload before continuing.")
