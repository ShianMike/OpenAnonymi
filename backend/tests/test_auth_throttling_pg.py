"""Account budgets survive address changes and independent application instances."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.config import Settings
from app.db.durable import AttemptEvent
from app.db.models import RecoveryToken
from app.factory import create_app
from tests.intake_support import ORIGIN, PASSWORD, _login
from tests.mail_support import Mailbox

EMAIL = "intake-owner@example.invalid"


def independent_client(site):
    owner, _, engine, _, _ = site
    settings = Settings(
        **{**owner.app.state.settings.model_dump(), "trusted_proxy_hops": 1}, _env_file=None
    )
    return TestClient(create_app(settings, engine=engine))


def headers(index):
    return {"Origin": ORIGIN, "X-Forwarded-For": f"198.51.100.{index + 1}"}


@pytest.mark.parametrize("email", [EMAIL, "unknown@example.invalid"])
def test_password_guessing_shares_account_budget_across_addresses_and_restarts(intake_site, email):
    with independent_client(intake_site) as client:
        for index in range(20):
            response = client.post(
                "/api/v1/auth/sign-in", headers=headers(index),
                json={"email": email if index % 2 else "  " + email.upper() + "  ",
                      "password": "wrong-synthetic-password"},
            )
            assert response.status_code == 401
    with independent_client(intake_site) as restarted:
        response = restarted.post(
            "/api/v1/auth/sign-in", headers=headers(20),
            json={"email": email, "password": PASSWORD},
        )
        assert response.status_code == 429 and response.json()["code"] == "sign_in_limited"
        assert restarted.post(
            "/api/v1/auth/sign-in", headers=headers(21),
            json={"email": "another@example.invalid", "password": "wrong-synthetic-password"},
        ).status_code == 401
        with Session(intake_site[2]) as session, session.begin():
            subject = AttemptLimiter(
                intake_site[2], restarted.app.state.settings, scope="sign_in_address"
            )._digest(email)
            rows = session.scalars(select(AttemptEvent).where(
                AttemptEvent.scope == "sign_in_address", AttemptEvent.subject_hmac == subject
            )).all()
            assert len(rows) == 20 and all(len(row.subject_hmac) == 32 for row in rows)
            session.execute(update(AttemptEvent).where(
                AttemptEvent.id.in_([row.id for row in rows])
            ).values(attempted_at=datetime.now(UTC) - timedelta(seconds=301)))
        assert restarted.post(
            "/api/v1/auth/sign-in", headers=headers(22),
            json={"email": email, "password": PASSWORD},
        ).status_code == (200 if email == EMAIL else 401)


def test_recovery_email_budget_survives_address_rotation_without_disclosing_accounts(intake_site):
    mailer = Mailbox()
    responses = []
    for index in range(4):
        with independent_client(intake_site) as client:
            client.app.state.recovery_mailer = mailer
            responses.append(client.post(
                "/api/v1/auth/recovery/request", headers=headers(index),
                json={"email": EMAIL if index % 2 else " " + EMAIL.upper() + " "},
            ))
    assert all(response.status_code == 202 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    assert len(mailer.messages) == 3
    with Session(intake_site[2]) as session:
        tokens = session.scalars(select(RecoveryToken).where(
            RecoveryToken.user_id == intake_site[4]
        )).all()
        assert len(tokens) == 3
    with independent_client(intake_site) as client:
        client.app.state.recovery_mailer = mailer
        for index in range(4):
            unknown = client.post(
                "/api/v1/auth/recovery/request", headers=headers(index + 10),
                json={"email": "unknown@example.invalid"},
            )
            assert unknown.status_code == 202 and unknown.json() == responses[0].json()
        assert len(mailer.messages) == 3
        # A delivered code still works when requesting more mail is limited.
        completed = client.post(
            "/api/v1/auth/recovery/complete", headers=headers(30),
            json={"email": EMAIL, "code": mailer.latest(EMAIL),
                  "new_password": "new-synthetic-recovery-password"},
        )
        assert completed.status_code == 204


def test_current_password_guesses_remain_bounded_across_sessions(intake_site):
    owner = intake_site[0]
    csrf = _login(owner, EMAIL)
    for _ in range(8):
        response = owner.post(
            "/api/v1/auth/change-password", headers=csrf,
            json={"current_password": "wrong-synthetic-password", "new_password": PASSWORD + "-new"},
        )
        assert response.status_code == 400
    with independent_client(intake_site) as restarted:
        second_csrf = _login(restarted, EMAIL)
        response = restarted.post(
            "/api/v1/auth/change-password", headers=second_csrf,
            json={"current_password": PASSWORD, "new_password": PASSWORD + "-new"},
        )
        assert response.status_code == 429 and response.json()["code"] == "password_change_limited"
        assert owner.get("/api/v1/auth/session").status_code == 200
