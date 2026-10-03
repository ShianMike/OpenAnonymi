"""Shared sliding-window budgets. Subjects are keyed digests, never stored raw."""

import base64
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import distinct, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.durable import AttemptEvent


class AttemptLimiter:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        scope: str,
        maximum: int = 8,
        window_seconds: int = 300,
        network_scope: bool = True,
        subject_cap: int = 10_000,
    ) -> None:
        if not scope or len(scope) > 64 or not 1 <= window_seconds <= 86400 or maximum < 1:
            raise ValueError("Invalid attempt-budget configuration.")
        self.engine, self.scope = engine, scope
        self.maximum, self.window_seconds = maximum, window_seconds
        self.network_scope, self.subject_cap = network_scope, subject_cap
        if settings.active_key_id:
            material = base64.urlsafe_b64decode(
                settings.content_keys[settings.active_key_id].get_secret_value()
            )
            self.key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=b"openanonymi-attempt-subjects-v1",
            ).derive(material)
        else:
            self.key = settings._attempt_subject_key

    def _digest(self, value: str) -> bytes:
        return hmac.digest(self.key, value.encode("utf-8"), "sha256")

    def take(
        self, subject: str, *, now: datetime | None = None, session: Session | None = None
    ) -> bool:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("A timezone-aware clock is required.")
        if session is None:
            with Session(self.engine) as owned, owned.begin():
                return self.take(subject, now=now, session=owned)
        digest = self._digest(subject)
        cutoff = now - timedelta(seconds=self.window_seconds)
        subject_lock = int.from_bytes(
            self._digest(self.scope + ":" + digest.hex())[:8], "big", signed=True
        )
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": subject_lock})
        if self.network_scope:
            scope_lock = int.from_bytes(self._digest("scope:" + self.scope)[:8], "big", signed=True)
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": scope_lock})
        active = (AttemptEvent.scope == self.scope, AttemptEvent.attempted_at > cutoff)
        count = session.scalar(
            select(func.count())
            .select_from(AttemptEvent)
            .where(*active, AttemptEvent.subject_hmac == digest)
        )
        if count >= self.maximum:
            return False
        if self.network_scope and count == 0:
            subjects = session.scalar(
                select(func.count(distinct(AttemptEvent.subject_hmac))).where(*active)
            )
            if subjects >= self.subject_cap:
                return False
        session.add(
            AttemptEvent(id=uuid4(), scope=self.scope, subject_hmac=digest, attempted_at=now)
        )
        return True
