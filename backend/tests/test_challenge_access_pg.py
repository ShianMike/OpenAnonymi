"""Real pre-session proof and newly issued cookies/keys are guarded after work and JSON."""

from datetime import UTC, datetime, timedelta
from time import sleep

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.security import COOKIE_NAME, _digest
from app.db.email_verification import PendingRegistration
from app.db.models import User
from app.db.second_factor import AuthChallenge, UserBackupCode
from tests.challenge_access_support import (
    OPERATIONS,
    after_prepared,
    after_serialized,
    challenge_case,
    cleanup_signup,
    fingerprint,
    lose_access,
    perform,
)
from tests.intake_support import _login


def deny(response, status, case):
    assert response.status_code == status
    assert response.headers['cache-control'] == 'no-store'
    body = response.json()
    assert {'code','message'} <= set(body) <= {'code','message','details'}
    assert not body.get('details')
    assert 'csrf_token' not in body and case['email'] not in response.text
    assert 'manual_key' not in body and 'backup_codes' not in body
    assert not any(COOKIE_NAME+'=' in line and 'Max-Age=0' not in line
                   for line in response.headers.get_list('set-cookie'))


@pytest.mark.parametrize('operation',OPERATIONS[:-1])
def test_prepared_authentication_rechecks_current_membership_before_commit(intake_site,monkeypatch,operation):
    case = challenge_case(intake_site,operation)
    before = fingerprint(case)
    fired = after_prepared(monkeypatch,case,lambda:lose_access(case))
    deny(perform(case),401,case)
    assert fired and fingerprint(case) == before
    assert not case['mailer'].notices


@pytest.mark.parametrize('operation',OPERATIONS)
@pytest.mark.parametrize('change',('membership','disabled'))
def test_serialized_new_authentication_withholds_private_body_and_cookie(intake_site,monkeypatch,operation,change):
    case = challenge_case(intake_site,operation)
    try:
        fired = after_serialized(monkeypatch,case,lambda:lose_access(case,change))
        response = perform(case)
        deny(response,401,case)
        assert fired
        # A successful activation/code use committed before this body was denied.
        expected = ['backup_code_used'] if operation == 'factor-finish' else ['second_factor_enabled'] if operation == 'forced-finish' else []
        assert [notice[1] for notice in case['mailer'].notices] == expected
    finally:
        cleanup_signup(case)


@pytest.mark.parametrize('operation',('password-sign-in','factor-finish','forced-finish','signup-verify'))
@pytest.mark.parametrize('change',('session','session-expired'))
def test_private_new_session_responses_validate_the_actual_issued_token(intake_site,monkeypatch,operation,change):
    case = challenge_case(intake_site,operation)
    try:
        fired = after_serialized(monkeypatch,case,lambda:lose_access(case,change))
        deny(perform(case),401,case)
        assert fired
    finally:
        cleanup_signup(case)


@pytest.mark.parametrize('operation',('challenge-sign-in','forced-start'))
@pytest.mark.parametrize('change',('consumed','challenge-expired'))
def test_serialized_challenge_or_qr_response_rechecks_its_own_capability(intake_site,monkeypatch,operation,change):
    case = challenge_case(intake_site,operation)
    fired = after_serialized(monkeypatch,case,lambda:lose_access(case,change))
    response = perform(case)
    deny(response,401,case)
    assert fired
    assert not any('openanonymi_challenge=' in line and 'Max-Age=0' not in line
                   for line in response.headers.get_list('set-cookie'))


@pytest.mark.parametrize('operation',('factor-finish','forced-start','forced-finish'))
def test_real_challenge_expiry_during_prepared_work_rolls_back_authentication(intake_site,monkeypatch,operation):
    case = challenge_case(intake_site,operation)
    expiry = datetime.now(UTC) + timedelta(seconds=2)
    token = case['client'].cookies.get('openanonymi_challenge')
    with Session(case['engine']) as session,session.begin():
        row = session.scalar(select(AuthChallenge).where(AuthChallenge.token_digest == _digest(token)))
        row.expires_at = expiry
    before = fingerprint(case)
    fired = after_prepared(monkeypatch,case,lambda:sleep(max(0,(expiry-datetime.now(UTC)).total_seconds())+0.02))
    deny(perform(case),401,case)
    assert fired and fingerprint(case) == before
    assert not case['mailer'].notices


def test_real_email_proof_expiry_during_decryption_cannot_create_an_account(intake_site,monkeypatch):
    from app.accounts.signup import KeyRing

    case = challenge_case(intake_site,'signup-verify')
    expiry = datetime.now(UTC) + timedelta(seconds=2)
    with Session(case['engine']) as session,session.begin():
        row = session.scalar(select(PendingRegistration).where(PendingRegistration.canonical_email == case['email']))
        row.expires_at = expiry
    original,fired = KeyRing.decrypt_text,[]

    def decrypted(*args,**kwargs):
        result = original(*args,**kwargs)
        fired.append(True)
        sleep(max(0,(expiry-datetime.now(UTC)).total_seconds())+0.02)
        return result

    monkeypatch.setattr(KeyRing,'decrypt_text',decrypted)
    try:
        deny(perform(case),400,case)
        assert fired
        with Session(case['engine']) as session:
            assert session.scalar(select(User.id).where(User.email == case['email'])) is None
            assert session.scalar(select(PendingRegistration).where(PendingRegistration.canonical_email == case['email'])) is not None
    finally:
        cleanup_signup(case)


@pytest.mark.parametrize('operation',OPERATIONS)
def test_authorized_authentication_keeps_its_real_contract_with_another_request_cookie(intake_site,operation):
    case = challenge_case(intake_site,operation)
    _login(case['other'],'intake-other@example.invalid')
    for cookie in case['other'].cookies.jar:
        if cookie.name == COOKIE_NAME:
            case['client'].cookies.jar.set_cookie(cookie)
    try:
        result = perform(case)
        assert result.status_code == (202 if operation == 'challenge-sign-in' else 201 if operation == 'signup-verify' else 200)
        if operation not in ('challenge-sign-in','forced-start'):
            view = result.json().get('session') or result.json()
            assert view['email'] == case['email'] and view['csrf_token']
            assert case['client'].get('/api/v1/auth/session').json()['email'] == case['email']
    finally:
        cleanup_signup(case)


def test_forced_backup_codes_are_withheld_if_used_during_serialization(intake_site,monkeypatch):
    case = challenge_case(intake_site,'forced-finish')

    def used():
        with Session(case['engine']) as session,session.begin():
            row = session.scalar(select(UserBackupCode).where(UserBackupCode.user_id == case['actor']))
            row.used_at = datetime.now(UTC)

    fired = after_serialized(monkeypatch,case,used)
    response = perform(case)
    deny(response,409,case)
    assert fired and response.json()['code'] == 'backup_codes_changed'
    assert [notice[1] for notice in case['mailer'].notices] == ['second_factor_enabled']


def test_forced_qr_is_withheld_when_an_actual_new_enrollment_supersedes_it(intake_site,monkeypatch):
    case = challenge_case(intake_site,'forced-start')

    def superseded():
        assert perform(case).status_code == 200

    fired = after_serialized(monkeypatch,case,superseded)
    response = perform(case)
    deny(response,409,case)
    assert fired and response.json()['code'] == 'enrollment_changed'


def test_late_workspace_factor_policy_change_rolls_back_a_password_only_session(intake_site,monkeypatch):
    from app.db.models import Workspace

    case = challenge_case(intake_site,'password-sign-in')
    before = fingerprint(case)

    def required():
        with Session(case['engine']) as session,session.begin():
            session.get(Workspace,case['workspace']).require_second_factor = True

    fired = after_prepared(monkeypatch,case,required)
    response = perform(case)
    deny(response,409,case)
    assert fired and response.json()['code'] == 'session_changed' and fingerprint(case) == before
    retry = perform(case)
    assert retry.status_code == 202 and retry.json()['status'] == 'enrollment_required'


@pytest.mark.parametrize('operation',('password-sign-in','factor-finish','forced-finish','signup-verify'))
def test_new_token_is_rechecked_after_actual_session_metadata_validation(intake_site,monkeypatch,operation):
    from app.accounts import api, second_factor_api

    case = challenge_case(intake_site,operation)
    module = second_factor_api if operation in ('factor-finish','forced-finish') else api
    original,fired = module.validate_session_view,[]

    def validated(*args,**kwargs):
        original(*args,**kwargs)
        if not fired:
            fired.append(True)
            lose_access(case,'session')

    monkeypatch.setattr(module,'validate_session_view',validated)
    try:
        deny(perform(case),401,case)
        assert fired
    finally:
        cleanup_signup(case)


@pytest.mark.parametrize('change',('membership','consumed','challenge-expired'))
def test_forced_setup_rechecks_capability_after_real_secret_decryption(intake_site,monkeypatch,change):
    from app.accounts.second_factor import KeyRing

    case = challenge_case(intake_site,'forced-start')
    original,fired = KeyRing.decrypt_text,[]

    def decrypted(*args,**kwargs):
        result = original(*args,**kwargs)
        if not fired:
            fired.append(True)
            lose_access(case,change)
        return result

    monkeypatch.setattr(KeyRing,'decrypt_text',decrypted)
    deny(perform(case),401,case)
    assert fired
