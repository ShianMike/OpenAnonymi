"""Fixed security email templates; delivery happens only after committed changes."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

CHANGES = {
    "second_factor_enabled": "Two-step verification was enabled.",
    "second_factor_disabled": "Two-step verification was disabled.",
    "second_factor_reset": "Your authenticator was reset; enrollment is required at your next sign-in.",
    "backup_codes_regenerated": "Your backup codes were regenerated.",
    "backup_code_used": "A backup code was used.",
    "password_changed": "Your password was changed.",
    "other_sessions_signed_out": "Other sessions were signed out.",
    "second_factor_attempts_exceeded": "Too many authenticator attempts were made.",
}


@dataclass(frozen=True)
class SecurityNotice:
    recipient: str
    event: str
    at: datetime


def notice_body(event: str, at: datetime) -> str:
    change = CHANGES[event]
    timestamp = at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"{change}\n{timestamp}\nIf you did not make this change, change your password and contact your workspace administrator."


def deliver_notice(mailer, notice: SecurityNotice) -> None:
    if mailer is None or not hasattr(mailer, "send_security_notice"):
        return
    try:
        mailer.send_security_notice(notice.recipient, notice.event, notice.at)
    except Exception:  # noqa: BLE001 - best-effort delivery after the security transaction commits
        # Notice delivery is a best-effort boundary after commit. Unexpected
        # mailer/formatting errors must not turn a completed change into a 500.
        logging.getLogger("app.accounts").warning(
            "security_notice_delivery_failed:%s", notice.event
        )
