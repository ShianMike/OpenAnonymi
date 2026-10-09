"""One-time recovery codes delivered through configured SMTP."""

import hashlib
import secrets
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts.email_rules import lookup_forms
from app.accounts.email_template import email_html
from app.accounts.security import hash_password
from app.config import Settings
from app.db.models import RecoveryToken, User
from app.db.models import Session as StoredSession

RECOVERY_TTL = timedelta(minutes=30)


class RecoveryDeliveryError(RuntimeError):
    pass


class InvalidRecoveryCode(RuntimeError):
    pass


class RecoveryMailer(Protocol):
    def send_recovery_code(self, recipient: str, code: str) -> None: ...

    def send_invitation_code(self, recipient: str, code: str) -> None: ...
    def send_registration_code(self, recipient: str, code: str) -> None: ...
    def send_email_verification_code(self, recipient: str, code: str) -> None: ...
    def send_security_notice(self, recipient: str, event: str, at: datetime) -> None: ...
    def send_notification(self, recipient: str, event: str) -> None: ...


class SmtpRecoveryMailer:
    def __init__(self, settings: Settings) -> None:
        if not all(
            (
                settings.smtp_host,
                settings.smtp_username,
                settings.smtp_password,
                settings.smtp_from,
            )
        ):
            raise ValueError("SMTP recovery is not configured.")
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_username
        self.password = settings.smtp_password
        self.sender = settings.smtp_from
        self.reply_to = settings.smtp_reply_to

    def send_recovery_code(self, recipient: str, code: str) -> None:
        self._send_code(
            recipient,
            code,
            "OpenAnonymi account recovery code",
            "Use this one-time code in the OpenAnonymi account recovery form:",
            "It expires in 30 minutes. If you did not request it, ignore this email.",
        )

    def send_invitation_code(self, recipient: str, code: str) -> None:
        self._send_code(
            recipient,
            code,
            "OpenAnonymi workspace invitation",
            "An administrator invited you to OpenAnonymi. Use this code in the "
            "Recover account form to set your password:",
            "It expires in 24 hours. If you did not expect it, ignore this email.",
        )

    def send_registration_code(self, recipient: str, code: str) -> None:
        self._send_code(
            recipient,
            code,
            "OpenAnonymi sign-up code",
            "Enter this code with the password you chose to finish signing up:",
            "It expires in 15 minutes. If you did not request it, ignore this email.",
        )

    def send_email_verification_code(self, recipient: str, code: str) -> None:
        self._send_code(
            recipient,
            code,
            "Verify your OpenAnonymi email",
            "Enter this code in Settings to verify your email:",
            "It expires in 15 minutes. If you did not request it, ignore this email.",
        )

    def _send_code(
        self, recipient: str, code: str, subject: str, introduction: str, expiry: str
    ) -> None:
        self._send_message(recipient, subject, f"{introduction}\n\n{code}\n\n{expiry}", code=code)

    def send_security_notice(self, recipient: str, event: str, at: datetime) -> None:
        from app.accounts.security_notices import notice_body

        self._send_message(recipient, "OpenAnonymi security notice", notice_body(event, at))

    def send_notification(self, recipient: str, event: str) -> None:
        from app.notifications.emails import SUBJECT, notification_body

        self._send_message(recipient, SUBJECT, notification_body(event))

    def _send_message(self, recipient: str, subject: str, body: str, *, code: str | None = None) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        sender = message["From"].addresses[0]
        if not sender.display_name:
            message.replace_header("From", Address("OpenAnonymi", addr_spec=sender.addr_spec))
        contact = self.reply_to or sender.addr_spec
        if self.reply_to:
            message["Reply-To"] = self.reply_to
        message["To"] = recipient
        message["Subject"] = subject
        message["Date"] = format_datetime(datetime.now(UTC))
        message["Message-ID"] = make_msgid(domain=message["From"].addresses[0].domain)
        message.set_content(f"{body}\n\nNeed help? Contact {contact}. Never share your code with support.")
        message.add_alternative(email_html(subject, body, contact=contact, code=code), subtype="html")
        try:
            context = ssl.create_default_context()
            connection = (
                smtplib.SMTP(self.host, self.port, timeout=10) if self.port == 587
                else smtplib.SMTP_SSL(self.host, self.port, timeout=10, context=context)
            )
            with connection:
                if self.port == 587:
                    connection.starttls(context=context)
                connection.login(self.username, self.password.get_secret_value())
                connection.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise RecoveryDeliveryError("Account recovery delivery failed.") from exc


def _digest(code: str) -> bytes:
    return hashlib.sha256(code.encode("ascii")).digest()


def request_recovery(
    session: Session, *, email: str, now: datetime, mailer: RecoveryMailer
) -> None:
    try:
        forms = lookup_forms(email)
    except ValueError:
        return
    with session.begin():
        user = session.scalar(select(User).where(User.email.in_(forms)))
        if user is None or user.disabled_at is not None:
            return
        code = secrets.token_urlsafe(24)
        token = RecoveryToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=_digest(code),
            created_at=now,
            expires_at=now + RECOVERY_TTL,
        )
        session.add(token)
        session.flush()
        mailer.send_recovery_code(user.email, code)


def complete_recovery(
    session: Session, *, email: str, code: str, new_password: str, now: datetime
) -> str:
    from app.db.second_factor import AuthChallenge, UserSecondFactor

    try:
        forms = lookup_forms(email)
        digest = _digest(code)
    except (ValueError, UnicodeEncodeError):
        raise InvalidRecoveryCode("The recovery code is invalid or expired.") from None
    new_hash = hash_password(new_password)
    with session.begin():
        user_id = session.scalar(select(RecoveryToken.user_id).where(RecoveryToken.token_hash == digest))
        if user_id is None:
            raise InvalidRecoveryCode("The recovery code is invalid or expired.")
        # Each completion consumes all account codes; lock the account before any token.
        user = session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.disabled_at is not None or user.email not in forms:
            raise InvalidRecoveryCode("The recovery code is invalid or expired.")
        token = session.scalar(select(RecoveryToken).where(
            RecoveryToken.token_hash == digest, RecoveryToken.user_id == user.id,
        ).with_for_update())
        if token is None or token.used_at is not None or token.expires_at <= datetime.now(UTC):
            raise InvalidRecoveryCode("The recovery code is invalid or expired.")
        user.password_hash = new_hash
        user.email_verified_at = now
        factor = session.get(UserSecondFactor, user.id)
        if factor is not None:
            factor.failed_attempts = 0
        session.execute(
            update(AuthChallenge)
            .where(AuthChallenge.user_id == user.id, AuthChallenge.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        session.execute(
            update(RecoveryToken)
            .where(RecoveryToken.user_id == user.id, RecoveryToken.used_at.is_(None))
            .values(used_at=now)
        )
        session.execute(
            update(StoredSession)
            .where(StoredSession.user_id == user.id, StoredSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        recipient = user.email
        session.flush()
        if token.expires_at <= datetime.now(UTC):
            raise InvalidRecoveryCode("The recovery code is invalid or expired.")
    return recipient
