"""Owned real password/challenge/email proof cases; private credentials stay in memory."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.accounts.api import ChallengeView, SessionView
from app.accounts.second_factor_api import EnrollmentView, ForcedEnrollmentView
from app.db.email_verification import PendingRegistration
from app.db.models import AuditEvent, Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.db.second_factor import AuthChallenge, UserBackupCode, UserSecondFactor
from tests.intake_support import ORIGIN, PASSWORD
from tests.mail_support import Mailbox
from tests.second_factor_support import enroll, password_step, totp

OPERATIONS=("password-sign-in", "challenge-sign-in", "factor-finish", "forced-start", "forced-finish", "signup-verify")

def challenge_case(site, operation):
    client, other, engine, workspace, actor = site
    case={"client":client,"other":other,"engine":engine,"workspace":workspace,"actor":actor,"operation":operation,
          "headers":{"Origin":ORIGIN},"email":"intake-owner@example.invalid"}
    client.app.state.recovery_mailer=case["mailer"]=Mailbox()
    if operation=="signup-verify":
        case["email"]=f"signup-{uuid4().hex[:12]}@openanonymi.test"
        client.app.state.settings.email_allow_test_domains=True
        result=client.post('/api/v1/auth/sign-up',headers=case['headers'],json={
            'email':case['email'],'password':PASSWORD,'workspace_name':'Fictional new-session workspace'})
        assert result.status_code==202
        case.update(path='/api/v1/auth/sign-up/verify',body={'email':case['email'],'password':PASSWORD,
            'code':case['mailer'].latest(case['email'])},model=SessionView)
    elif operation=='password-sign-in':
        case.update(path='/api/v1/auth/sign-in',body={'email':case['email'],'password':PASSWORD},model=SessionView)
    elif operation in ('challenge-sign-in','factor-finish'):
        _, _, codes=enroll(client)
        assert client.post('/api/v1/auth/sign-out',headers=_current_headers(client)).status_code==204
        if operation=='challenge-sign-in':
            case.update(path='/api/v1/auth/sign-in',body={'email':case['email'],'password':PASSWORD},model=ChallengeView)
        else:
            password_step(client)
            case.update(path='/api/v1/auth/sign-in/second-factor',body={'code':codes[0]},model=SessionView)
    else:
        with Session(engine) as session,session.begin():
            session.get(User,actor).second_factor_reenroll_required=True
        password_step(client)
        case.update(path='/api/v1/auth/sign-in/enrollment/start',body=None,model=EnrollmentView)
        if operation=='forced-finish':
            start=perform(case)
            assert start.status_code==200
            case.update(path='/api/v1/auth/sign-in/enrollment/confirm',body={'code':totp(start.json()['manual_key'])},
                        model=ForcedEnrollmentView)
    case['mailer'].messages.clear()
    case['mailer'].notices.clear()
    return case

def _current_headers(client):
    return {'Origin':ORIGIN,'X-CSRF-Token':client.get('/api/v1/auth/session').json()['csrf_token']}

def perform(case):
    return case['client'].post(case['path'],headers=case['headers'],json=case['body'])

def lose_access(case,change='membership'):
    with Session(case['engine']) as session,session.begin():
        user=session.scalar(select(User).where(User.email==case['email']))
        assert user is not None
        case['issued_actor']=user.id
        if change=='membership':
            for row in session.scalars(select(Membership).where(Membership.user_id==user.id)):
                row.revoked_at=datetime.now(UTC)
        elif change=='disabled':
            user.disabled_at=datetime.now(UTC)
        elif change in ('session','session-expired'):
            rows=session.scalars(select(StoredSession).where(StoredSession.user_id==user.id,StoredSession.revoked_at.is_(None))).all()
            assert rows
            for row in rows:
                if change=='session': row.revoked_at=datetime.now(UTC)
                else: row.created_at,row.expires_at=datetime.now(UTC)-timedelta(days=1),datetime.now(UTC)-timedelta(seconds=1)
        else:
            rows=session.scalars(select(AuthChallenge).where(AuthChallenge.user_id==user.id,AuthChallenge.consumed_at.is_(None))).all()
            assert rows
            for row in rows:
                if change=='consumed': row.consumed_at=datetime.now(UTC)
                else: row.created_at,row.expires_at=datetime.now(UTC)-timedelta(days=1),datetime.now(UTC)-timedelta(seconds=1)

def after_serialized(monkeypatch,case,change):
    import fastapi.routing
    original_json=case['model'].model_dump_json
    original_fastapi=fastapi.routing.serialize_response
    fired=[]
    def serialized(*args,**kwargs):
        result=original_json(*args,**kwargs)
        if not fired:
            fired.append(True);change()
        return result
    async def serialized_fastapi(*args,**kwargs):
        result=await original_fastapi(*args,**kwargs)
        if not fired:
            fired.append(True);change()
        return result
    monkeypatch.setattr(case['model'],'model_dump_json',serialized)
    monkeypatch.setattr(fastapi.routing,'serialize_response',serialized_fastapi)
    return fired

def after_prepared(monkeypatch,case,change):
    from app.accounts import challenges
    module,hook=(challenges,'password_step') if case['operation'].endswith('sign-in') else (
        challenges,'start_locked_enrollment' if case['operation']=='forced-start' else
        'activate_locked' if case['operation']=='forced-finish' else 'consume_code')
    original,fired=getattr(module,hook),[]
    def prepared(*args,**kwargs):
        result=original(*args,**kwargs)
        if not fired:
            fired.append(True);change()
        return result
    monkeypatch.setattr(module,hook,prepared)
    return fired

def fingerprint(case):
    with Session(case['engine']) as session:
        return tuple(tuple(sorted([tuple(getattr(row,col.name) for col in model.__table__.columns)
            for row in session.scalars(select(model).where(condition))],key=repr)) for model,condition in (
                (User,User.id==case['actor']),
                (StoredSession,StoredSession.user_id==case['actor']),
                (UserSecondFactor,UserSecondFactor.user_id==case['actor']),
                (UserBackupCode,UserBackupCode.user_id==case['actor']),
                (AuthChallenge,AuthChallenge.user_id==case['actor']),
                (AuditEvent,AuditEvent.workspace_id==case['workspace'])))

def cleanup_signup(case):
    if case['operation']!='signup-verify':return
    with Session(case['engine']) as session,session.begin():
        user=session.scalar(select(User).where(User.email==case['email']))
        session.execute(delete(PendingRegistration).where(PendingRegistration.canonical_email==case['email']))
        if user is None:return
        ids=session.scalars(select(Membership.workspace_id).where(Membership.user_id==user.id)).all()
        session.execute(delete(Membership).where(Membership.user_id==user.id));session.delete(user);session.flush()
        session.execute(delete(Workspace).where(Workspace.id.in_(ids)))
