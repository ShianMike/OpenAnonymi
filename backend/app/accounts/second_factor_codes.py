"""TOTP and backup-code primitives without network calls or persistent raw codes."""

import base64
import hashlib
import re
import secrets
from datetime import datetime

import segno
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.twofactor import InvalidToken
from cryptography.hazmat.primitives.twofactor.totp import TOTP


def normalize_code(value: str) -> str:
    compact = "".join(value.split())
    if re.fullmatch(r"[0-9]{6}", compact):
        return compact
    backup = compact.replace("-", "").upper()
    if re.fullmatch(r"[A-Z2-7]{16}", backup):
        return backup
    return ""


def new_manual_key() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def matching_step(
    manual_key: str, code: str, now: datetime, last_used_step: int | None
) -> int | None:
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    generator = TOTP(base64.b32decode(manual_key), 6, hashes.SHA1(), 30)
    step = int(now.timestamp()) // 30
    matches = []
    for candidate in (step - 1, step, step + 1):
        if candidate < 0:
            continue
        try:
            generator.verify(code.encode("ascii"), candidate * 30)
            matches.append(candidate)
        except InvalidToken:
            pass
    latest = max(matches, default=-1)
    return latest if latest > (last_used_step if last_used_step is not None else -1) else None


def backup_digest(code: str) -> bytes:
    return hashlib.sha256(code.encode("ascii")).digest()


def new_backup_codes() -> list[str]:
    codes = [base64.b32encode(secrets.token_bytes(10)).decode() for _ in range(10)]
    return ["-".join(code[i : i + 4] for i in range(0, 16, 4)) for code in codes]


def qr_path(manual_key: str, email: str) -> tuple[str, int]:
    generator = TOTP(base64.b32decode(manual_key), 6, hashes.SHA1(), 30)
    uri = generator.get_provisioning_uri(email, "OpenAnonymi")
    qr = segno.make_qr(uri, error="M", boost_error=False)
    # Only geometry is returned. React draws it inline; no HTML or remote image.
    path = "".join(
        f"M{x + 4} {y + 4}h1v1h-1z"
        for y, row in enumerate(qr.matrix)
        for x, dark in enumerate(row)
        if dark
    )
    return path, len(qr.matrix) + 8
