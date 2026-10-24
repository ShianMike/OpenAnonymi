"""Short email codes are keyed and bound to both the mailbox and their purpose."""

import hashlib
import hmac
import secrets
from collections.abc import Collection

from app.accounts.limits import subject_key
from app.config import Settings


def code_digest(settings: Settings, purpose: str, recipient: str, code: str) -> bytes:
    value = f"openanonymi-email-code-v1\0{purpose}\0{recipient}\0{code}"
    return hmac.digest(subject_key(settings), value.encode("utf-8"), "sha256")


def code_digests(settings: Settings, purpose: str, recipient: str, code: str) -> tuple[bytes, ...]:
    current = code_digest(settings, purpose, recipient, code)
    # Previously issued long codes and invitations remain usable until their own expiry.
    if len(code) == 6 and code.isascii() and code.isdecimal():
        return (current,)
    try:
        return (current, hashlib.sha256(code.encode("ascii")).digest())
    except UnicodeEncodeError:
        return (current,)


def issue_code(
    settings: Settings, purpose: str, recipient: str, used: Collection[bytes],
) -> tuple[str, bytes]:
    for _ in range(10):
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = code_digest(settings, purpose, recipient, code)
        if digest not in used:
            return code, digest
    raise RuntimeError("Unable to issue a distinct email code.")
