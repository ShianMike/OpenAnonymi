"""Development-only delivery to a configured, ignored directory; no debug API."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.accounts.recovery import RecoveryDeliveryError


class OutboxMailer:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        if ".local-dev" not in self.directory.parts:
            raise ValueError("A .local-dev outbox directory is required.")

    def _write(self, recipient: str, code: str, subject: str, expiry: str):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            now = datetime.now(UTC)
            path = self.directory / (now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex + ".json")
            with path.open("x", encoding="utf-8") as output:
                json.dump(
                    {
                        "to": recipient,
                        "subject": subject,
                        "body": code + "\n\n" + expiry,
                        "created_at": now.isoformat(),
                    },
                    output,
                )
        except OSError:
            raise RecoveryDeliveryError("Email delivery failed.") from None

    def send_registration_code(self, recipient: str, code: str):
        self._write(recipient, code, "OpenAnonymi sign-up code", "Expires in 15 minutes.")

    def send_email_verification_code(self, recipient: str, code: str):
        self._write(recipient, code, "Verify your OpenAnonymi email", "Expires in 15 minutes.")

    def send_recovery_code(self, recipient: str, code: str):
        self._write(recipient, code, "OpenAnonymi account recovery code", "Expires in 30 minutes.")

    def send_invitation_code(self, recipient: str, code: str):
        self._write(recipient, code, "OpenAnonymi workspace invitation", "Expires in 24 hours.")

    def send_security_notice(self, recipient: str, event: str, at: datetime):
        from app.accounts.security_notices import notice_body

        self._write(recipient, notice_body(event, at), "OpenAnonymi security notice", "")

    def send_notification(self, recipient: str, event: str):
        from app.notifications.emails import SUBJECT, notification_body

        self._write(recipient, notification_body(event), SUBJECT, "")
