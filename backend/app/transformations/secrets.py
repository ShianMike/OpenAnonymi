"""Replacement secrets read once inside the authorized document transaction."""

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.crypto import KeyRing, ProtectedContentError, ProtectedValue
from app.db.replacement_secrets import DocumentReplacementSecret


@dataclass(frozen=True, repr=False)
class ReplacementSecret:
    seed: bytes
    offset: int


def random_offset() -> int:
    index = secrets.randbelow(672)
    return index - 365 if index < 336 else index - 306


def load_secret(session: Session, document_id: UUID, keys: KeyRing) -> ReplacementSecret:
    row = session.get(DocumentReplacementSecret, document_id)
    if row is None:
        raise ProtectedContentError("Replacement configuration is unavailable.")
    try:
        value = json.loads(keys.decrypt_text(ProtectedValue(row.secret_ciphertext, row.key_id)))
        seed = bytes.fromhex(value["seed"])
        offset = value["offset"]
        if (
            value["version"] != 1
            or len(seed) != 32
            or type(offset) is not int
            or not 30 <= abs(offset) <= 365
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ProtectedContentError("Replacement configuration is unavailable.") from None
    return ReplacementSecret(seed, offset)


def ensure_secret(
    session: Session, document_id: UUID, keys: KeyRing, now: datetime
) -> ReplacementSecret:
    """Caller holds the document lock; retries reuse the committed row."""
    if session.get(DocumentReplacementSecret, document_id) is not None:
        return load_secret(session, document_id, keys)
    seed, offset = secrets.token_bytes(32), random_offset()
    protected = keys.encrypt_text(
        json.dumps({"version": 1, "seed": seed.hex(), "offset": offset}, separators=(",", ":"))
    )
    session.add(
        DocumentReplacementSecret(
            document_id=document_id,
            secret_ciphertext=protected.ciphertext,
            key_id=protected.key_id,
            created_at=now,
        )
    )
    session.flush()
    return ReplacementSecret(seed, offset)
