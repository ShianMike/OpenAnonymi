"""Real authenticator codes and API enrollment against the isolated PostgreSQL fixture."""

import base64
from datetime import UTC, datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.twofactor.totp import TOTP

from tests.intake_support import ORIGIN, PASSWORD, _login


def totp(key, now=None):
    return (
        TOTP(base64.b32decode(key), 6, hashes.SHA1(), 30)
        .generate((now or datetime.now(UTC)).timestamp())
        .decode()
    )


def invalid_code(key, now=None):
    now = (now or datetime.now(UTC)).timestamp()
    generator = TOTP(base64.b32decode(key), 6, hashes.SHA1(), 30)
    valid = {generator.generate(now + offset).decode() for offset in (-30, 0, 30)}
    return next(f"{i:06}" for i in range(4) if f"{i:06}" not in valid)


def enroll(client, *, email="intake-owner@example.invalid"):
    headers = _login(client, email)
    start = client.post("/api/v1/auth/second-factor/enrollment/start", headers=headers)
    assert start.status_code == 200
    key = start.json()["manual_key"]
    confirmed = client.post(
        "/api/v1/auth/second-factor/enrollment/confirm", headers=headers, json={"code": totp(key)}
    )
    assert confirmed.status_code == 200
    return headers, key, confirmed.json()["backup_codes"]


def password_step(client, email="intake-owner@example.invalid"):
    result = client.post(
        "/api/v1/auth/sign-in",
        headers={"Origin": ORIGIN},
        json={"email": email, "password": PASSWORD},
    )
    assert result.status_code == 202
    assert "csrf_token" not in result.json() and "user_id" not in result.json()
    return result
