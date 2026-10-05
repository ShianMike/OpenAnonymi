"""Late session loss rolls back authenticator changes and denies private codes."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.second_factor_api import BackupCodesView, EnrollmentView
from app.db.crypto import KeyRing
from app.db.second_factor import UserBackupCode, UserSecondFactor
from tests.factor_access_support import (
    OPERATIONS,
    after_factor_work,
    factor_case,
    fingerprint,
    perform,
)
from tests.mail_support import Mailbox
from tests.test_content_read_access_pg import change_actor
from tests.test_intake_batch_lifecycle_access_pg import assert_denied


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("change", ("revoked", "expired", "membership"))
def test_authenticator_changes_roll_back_after_real_late_session_loss(
    intake_site, monkeypatch, operation, change
):
    case = factor_case(intake_site, operation)
    case["client"].app.state.recovery_mailer = mailer = Mailbox()
    before = fingerprint(case)
    fired = after_factor_work(monkeypatch, case, lambda: change_actor(case, change))
    assert_denied(perform(case), 401)
    assert fired and fingerprint(case) == before
    assert mailer.notices == []


@pytest.mark.parametrize("operation", OPERATIONS)
def test_authenticator_rechecks_after_actual_user_and_session_lock(
    intake_site, monkeypatch, operation
):
    from app.accounts import second_factor as service

    case = factor_case(intake_site, operation)
    before = fingerprint(case)
    original, fired = service.locked_user, []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change_actor(case, "revoked")
        return result

    monkeypatch.setattr(service, "locked_user", changed)
    assert_denied(perform(case), 401)
    assert fired and fingerprint(case) == before


def after_json(monkeypatch, operation, change):
    model = EnrollmentView if operation == "start" else BackupCodesView
    original, fired = model.model_dump_json, []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(model, "model_dump_json", changed)
    return fired


@pytest.mark.parametrize("operation", ("start", "confirm"))
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_committed_authenticator_changes_withhold_serialized_keys_or_codes(
    intake_site, monkeypatch, operation, change
):
    case = factor_case(intake_site, operation)
    case["client"].app.state.recovery_mailer = mailer = Mailbox()
    before = fingerprint(case)
    fired = after_json(monkeypatch, operation, lambda: change_actor(case, change))
    response = perform(case)
    assert_denied(response, 401)
    assert "manual_key" not in response.text and "backup_codes" not in response.text
    assert fired and fingerprint(case) != before
    assert len(mailer.notices) == (1 if operation == "confirm" else 0)


@pytest.mark.parametrize("operation", ("start", "confirm"))
def test_serialized_factor_generation_cannot_release_changed_or_consumed_secrets(
    intake_site, monkeypatch, operation
):
    case = factor_case(intake_site, operation)

    def changed_generation():
        with Session(case["engine"]) as session, session.begin():
            if operation == "start":
                factor = session.get(UserSecondFactor, case["actor"])
                keys = KeyRing.from_settings(case["client"].app.state.settings)
                protected = keys.encrypt_text("A" * 32)
                factor.secret_ciphertext, factor.key_id = protected.ciphertext, protected.key_id
            else:
                row = session.scalar(
                    select(UserBackupCode).where(
                        UserBackupCode.user_id == case["actor"], UserBackupCode.used_at.is_(None)
                    )
                )
                row.used_at = datetime.now(UTC)

    fired = after_json(monkeypatch, operation, changed_generation)
    response = perform(case)
    assert_denied(response, 409)
    assert "manual_key" not in response.text and '"backup_codes":' not in response.text
    assert fired and case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("operation", OPERATIONS)
def test_authorized_factor_changes_still_work(intake_site, operation):
    case = factor_case(intake_site, operation)
    response = perform(case)
    assert response.status_code == (204 if operation == "disable" else 200)
    assert case["client"].get("/api/v1/auth/session").status_code == 200
    if operation != "disable":
        assert response.headers["cache-control"] == "no-store"


def test_actual_next_step_regeneration_denies_late_session_and_preserves_old_codes(
    intake_site, monkeypatch
):
    case = factor_case(intake_site, "regenerate")
    before = fingerprint(case)
    fired = after_factor_work(monkeypatch, case, lambda: change_actor(case, "revoked"))
    assert_denied(perform(case), 401)
    assert fired and fingerprint(case) == before
