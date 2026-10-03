"""Best-effort immediate purge, retried by the durable maintenance pass."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.cleanup.service import purge_document
from app.db.models import Document

LOGGER = logging.getLogger(__name__)


def purge_deleted_document(engine: Engine, document_id: UUID) -> None:
    try:
        with Session(engine) as session, session.begin():
            document = session.get(Document, document_id)
            if document is not None:
                purge_document(session, document, datetime.now(UTC))
    except Exception:  # noqa: BLE001 -- after-commit task must never fail the deletion response
        LOGGER.warning("Immediate content cleanup failed; the next pass will retry.")
