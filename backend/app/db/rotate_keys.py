"""Re-encrypt protected database fields with the configured active Fernet key.

Run one worker. Each batch commits atomically and a failed run can be retried.
This command prints only record counts, never source text or ciphertext.
"""

from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import ConfigurationError, Settings, load_settings
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError, ProtectedValue
from app.db.custom_rules import RuleVersion
from app.db.email_verification import PendingRegistration
from app.db.models import Document, SourceRevision
from app.db.recovery import RecoverySnapshot
from app.db.second_factor import UserSecondFactor
from app.db.team_review import FindingComment

BATCH_SIZE = 100


def rotate_documents(session: Session, keys: KeyRing) -> int:
    rows = session.scalars(
        select(Document)
        .where(Document.title_ciphertext.is_not(None), Document.title_key_id != keys.active_key_id)
        .order_by(Document.id)
        .limit(BATCH_SIZE)
        .with_for_update()
    ).all()
    for document in rows:
        protected = ProtectedValue(document.title_ciphertext, document.title_key_id)
        rotated = keys.rotate_text(protected)
        document.title_ciphertext = rotated.ciphertext
        document.title_key_id = rotated.key_id
    return len(rows)


def rotate_sources(session: Session, keys: KeyRing) -> int:
    rows = session.scalars(
        select(SourceRevision)
        .where(SourceRevision.source_key_id != keys.active_key_id)
        .order_by(SourceRevision.id)
        .limit(BATCH_SIZE)
        .with_for_update()
    ).all()
    for revision in rows:
        protected = ProtectedValue(revision.source_ciphertext, revision.source_key_id)
        rotated = keys.rotate_text(protected)
        revision.source_ciphertext = rotated.ciphertext
        revision.source_key_id = rotated.key_id
    return len(rows)


def rotate_recovery(session: Session, keys: KeyRing) -> int:
    rows = session.scalars(
        select(RecoverySnapshot)
        .where(RecoverySnapshot.payload_key_id != keys.active_key_id)
        .order_by(RecoverySnapshot.id)
        .limit(BATCH_SIZE)
        .with_for_update()
    ).all()
    for row in rows:
        rotated = keys.rotate_text(ProtectedValue(row.payload_ciphertext, row.payload_key_id))
        row.payload_ciphertext, row.payload_key_id = rotated.ciphertext, rotated.key_id
    return len(rows)


def rotate_rules(session: Session, keys: KeyRing) -> int:
    rows = session.scalars(
        select(RuleVersion)
        .where(RuleVersion.payload_key_id != keys.active_key_id)
        .order_by(RuleVersion.rule_id, RuleVersion.version)
        .limit(BATCH_SIZE)
        .with_for_update()
    ).all()
    for row in rows:
        rotated = keys.rotate_text(ProtectedValue(row.payload_ciphertext, row.payload_key_id))
        row.payload_ciphertext, row.payload_key_id = rotated.ciphertext, rotated.key_id
    return len(rows)


def rotate_comments(session: Session, keys: KeyRing) -> int:
    rows = session.scalars(
        select(FindingComment)
        .where(FindingComment.text_key_id != keys.active_key_id)
        .order_by(FindingComment.id)
        .limit(BATCH_SIZE)
        .with_for_update()
    ).all()
    for row in rows:
        protected = keys.rotate_text(ProtectedValue(row.text_ciphertext, row.text_key_id))
        row.text_ciphertext, row.text_key_id = protected.ciphertext, protected.key_id
    return len(rows)


def rotate_pending_registrations(session: Session, keys: KeyRing) -> int:
    rows = session.scalars(
        select(PendingRegistration)
        .where(PendingRegistration.key_id != keys.active_key_id)
        .order_by(PendingRegistration.id)
        .limit(BATCH_SIZE)
        .with_for_update()
    ).all()
    for row in rows:
        rotated = keys.rotate_text(ProtectedValue(row.workspace_name_ciphertext, row.key_id))
        row.workspace_name_ciphertext, row.key_id = rotated.ciphertext, rotated.key_id
    return len(rows)


def rotate_second_factors(session: Session, keys: KeyRing) -> int:
    rows = session.scalars(
        select(UserSecondFactor)
        .where(UserSecondFactor.key_id != keys.active_key_id)
        .order_by(UserSecondFactor.user_id)
        .limit(BATCH_SIZE)
        .with_for_update()
    ).all()
    for row in rows:
        rotated = keys.rotate_text(ProtectedValue(row.secret_ciphertext, row.key_id))
        row.secret_ciphertext, row.key_id = rotated.ciphertext, rotated.key_id
    return len(rows)


def rotate_database(settings: Settings, keys: KeyRing) -> dict[str, int]:
    engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)
    totals = {
        "titles": 0,
        "source revisions": 0,
        "working drafts": 0,
        "rules": 0,
        "comments": 0,
        "pending registrations": 0,
        "authenticator secrets": 0,
    }
    try:
        for label, rotate_batch in (
            ("titles", rotate_documents),
            ("source revisions", rotate_sources),
            ("working drafts", rotate_recovery),
            ("rules", rotate_rules),
            ("comments", rotate_comments),
            ("pending registrations", rotate_pending_registrations),
            ("authenticator secrets", rotate_second_factors),
        ):
            while True:
                with Session(engine) as session:
                    if label == "source revisions":
                        session.info["allow_source_key_rotation"] = True
                        session.execute(text("SET LOCAL openanonymi.key_rotation = 'on'"))
                    count = rotate_batch(session, keys)
                    session.commit()
                totals[label] += count
                if count < BATCH_SIZE:
                    break
    finally:
        engine.dispose()
    return totals


def main() -> None:
    try:
        settings = load_settings()
        keys = KeyRing.from_settings(settings)
        totals = rotate_database(settings, keys)
    except (ConfigurationError, ContentKeyUnavailable, ProtectedContentError, SQLAlchemyError):
        raise SystemExit(
            "Key rotation failed. Check database access and configured content keys."
        ) from None
    print(
        f"Rotated {totals['titles']} titles, {totals['source revisions']} source revisions "
        f", {totals['working drafts']} working drafts, {totals['rules']} rule versions "
        f", {totals['comments']} finding comments "
        f", {totals['pending registrations']} pending registrations "
        f"and {totals['authenticator secrets']} authenticator secrets."
    )


if __name__ == "__main__":
    main()
