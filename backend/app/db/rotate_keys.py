"""Re-encrypt protected database fields with the configured active Fernet key.

Run one worker. Each batch commits atomically and a failed run can be retried.
This command prints only record counts, never source text or ciphertext.
"""

from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import ConfigurationError, load_settings
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError, ProtectedValue
from app.db.models import Document, SourceRevision

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


def main() -> None:
    try:
        settings = load_settings()
        keys = KeyRing.from_settings(settings)
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        totals = {"titles": 0, "source revisions": 0}
        try:
            for label, rotate_batch in (
                ("titles", rotate_documents),
                ("source revisions", rotate_sources),
            ):
                while True:
                    with Session(engine) as session:
                        count = rotate_batch(session, keys)
                        session.commit()
                    totals[label] += count
                    if count < BATCH_SIZE:
                        break
        finally:
            engine.dispose()
    except (ConfigurationError, ContentKeyUnavailable, ProtectedContentError, SQLAlchemyError):
        raise SystemExit(
            "Key rotation failed. Check database access and configured content keys."
        ) from None
    print(f"Rotated {totals['titles']} titles and {totals['source revisions']} source revisions.")


if __name__ == "__main__":
    main()
