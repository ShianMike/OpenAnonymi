"""Origin/CSRF-protected settings and HttpOnly challenge-protected pre-session steps."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.engine import Engine
from starlette.background import BackgroundTask

from app.accounts.api import (
    SessionView,
    _view,
    clear_challenge_cookie,
    clear_session_cookie,
    current_identity,
    mutation_identity,
    require_mutation_origin,
    set_session_cookie,
    validate_session_view,
)
from app.accounts.challenges import (
    CHALLENGE_NAME,
    finish_forced_enrollment,
    finish_password_step,
    start_forced_enrollment,
    validate_challenge,
)
from app.accounts.devices import list_devices, revoke_device, revoke_others
from app.accounts.response_boundary import protected_json_response
from app.accounts.second_factor import (
    FactorError,
    change_factor,
    confirm_enrollment,
    security_status,
    start_enrollment,
    validate_backup_codes,
    validate_enrollment,
)
from app.accounts.security import SessionIdentity
from app.accounts.security_notices import deliver_notice
from app.config import Settings
from app.contracts import ErrorResponse
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.errors import ApiError


class FactorCodeRequest(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=64)


class FactorChangeRequest(FactorCodeRequest):
    password: SecretStr = Field(min_length=1, max_length=1024)


class EnrollmentView(BaseModel):
    qr_svg_path: str
    qr_size: int
    manual_key: str
    expires_at: datetime


class BackupCodesView(BaseModel):
    backup_codes: list[str]


class ForcedEnrollmentView(BackupCodesView):
    session: SessionView


class SecondFactorState(BaseModel):
    enabled: bool
    pending_expires_at: datetime | None
    backup_codes_remaining: int
    locked: bool
    security_emails_available: bool


class DeviceView(BaseModel):
    id: UUID
    current: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    device_label: str
    auth_method: str


def factor_failure(error: FactorError, request: Request) -> JSONResponse:
    response = JSONResponse(
        {"code": error.code, "message": error.message},
        status_code=error.status,
        background=BackgroundTask(deliver_notice, request.app.state.recovery_mailer, error.notice)
        if error.notice
        else None,
    )
    if error.clear_challenge:
        clear_challenge_cookie(response, request.app.state.settings)
    return response


def create_second_factor_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/auth",
        tags=["account security"],
        responses={
            status: {"model": ErrorResponse} for status in (400, 401, 403, 404, 409, 422, 429, 503)
        },
    )

    def notices(background: BackgroundTasks, request: Request, delivered):
        for notice in delivered:
            background.add_task(deliver_notice, request.app.state.recovery_mailer, notice)

    def unavailable():
        raise ApiError(
            503, "second_factor_unavailable", "Authenticator setup is unavailable right now."
        ) from None

    def protected(view, request, identity, authorize, background=None, *, token=None):
        try:
            response = protected_json_response(view, request, identity, authorize, token=token)
        except ApiError as error:
            # The authorized change already committed: preserve its fixed
            # security notice even when the subsequent private body is denied.
            response = JSONResponse(
                status_code=error.status_code,
                content=ErrorResponse(code=error.code, message=error.message).model_dump(),
                headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
            )
        except (ContentKeyUnavailable, ProtectedContentError):
            response = JSONResponse(
                status_code=503,
                content=ErrorResponse(
                    code="second_factor_unavailable",
                    message="Authenticator setup is unavailable right now.",
                ).model_dump(),
                headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
            )
        response.background = background
        return response

    def issued_response(view, request, issued, background):
        def authorize(current):
            session_view = view.session if isinstance(view, ForcedEnrollmentView) else view
            validate_session_view(session_view, current, request.app.state.recovery_mailer is not None)
            if isinstance(view, ForcedEnrollmentView):
                validate_backup_codes(engine, current.user_id, view.backup_codes)

        response = protected(view, request, issued.identity, authorize, background, token=issued.token)
        clear_challenge_cookie(response, settings)
        if response.status_code == 200:
            set_session_cookie(response, issued.token, settings)
        return response

    @router.get("/second-factor", response_model=SecondFactorState)
    def state(request: Request, identity: Annotated[SessionIdentity, Depends(current_identity)]):
        def view(current):
            return SecondFactorState(
                **security_status(engine, current.user_id, datetime.now(UTC)),
                security_emails_available=request.app.state.recovery_mailer is not None,
            )

        prepared = view(identity)

        def authorize(current):
            if view(current) != prepared:
                raise ApiError(409, "security_state_changed", "Security settings changed. Reload to continue.")

        return protected(prepared, request, identity, authorize)

    @router.post("/second-factor/enrollment/start", response_model=EnrollmentView)
    def start(request: Request, identity: Annotated[SessionIdentity, Depends(mutation_identity)]):
        try:
            result = start_enrollment(
                engine,
                settings,
                identity.user_id,
                identity.session_id,
                datetime.now(UTC),
                reauthorize=lambda: current_identity(request),
            )
            view = EnrollmentView(**result.__dict__)
            return protected(
                view,
                request,
                identity,
                lambda current: validate_enrollment(
                    engine,
                    current.user_id,
                    view.manual_key,
                    view.expires_at,
                    KeyRing.from_settings(settings),
                ),
            )
        except FactorError as error:
            return factor_failure(error, request)
        except (ContentKeyUnavailable, ProtectedContentError):
            unavailable()

    @router.post("/second-factor/enrollment/confirm", response_model=BackupCodesView)
    def confirm(
        body: FactorCodeRequest,
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        try:
            codes, delivered = confirm_enrollment(
                engine,
                settings,
                identity.user_id,
                identity.session_id,
                body.code.get_secret_value(),
                datetime.now(UTC),
                reauthorize=lambda: current_identity(request),
            )
            notices(background, request, delivered)
            view = BackupCodesView(backup_codes=codes)
            return protected(
                view,
                request,
                identity,
                lambda current: validate_backup_codes(engine, current.user_id, codes),
                background,
            )
        except FactorError as error:
            return factor_failure(error, request)
        except (ContentKeyUnavailable, ProtectedContentError):
            unavailable()

    @router.post("/second-factor/disable", status_code=204)
    def disable(
        body: FactorChangeRequest,
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        try:
            _, delivered = change_factor(
                engine,
                settings,
                identity.user_id,
                identity.session_id,
                body.password.get_secret_value(),
                body.code.get_secret_value(),
                datetime.now(UTC),
                disable=True,
                reauthorize=lambda: current_identity(request),
            )
            notices(background, request, delivered)
            return Response(status_code=204, background=background)
        except FactorError as error:
            return factor_failure(error, request)
        except (ContentKeyUnavailable, ProtectedContentError):
            unavailable()

    @router.post("/second-factor/backup-codes", response_model=BackupCodesView)
    def regenerate(
        body: FactorChangeRequest,
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        try:
            codes, delivered = change_factor(
                engine,
                settings,
                identity.user_id,
                identity.session_id,
                body.password.get_secret_value(),
                body.code.get_secret_value(),
                datetime.now(UTC),
                disable=False,
                reauthorize=lambda: current_identity(request),
            )
            notices(background, request, delivered)
            view = BackupCodesView(backup_codes=codes)
            return protected(
                view,
                request,
                identity,
                lambda current: validate_backup_codes(engine, current.user_id, codes),
                background,
            )
        except FactorError as error:
            return factor_failure(error, request)
        except (ContentKeyUnavailable, ProtectedContentError):
            unavailable()

    @router.post("/sign-in/second-factor", response_model=SessionView)
    def finish(
        body: FactorCodeRequest, request: Request, background: BackgroundTasks
    ):
        require_mutation_origin(request)
        try:
            issued, delivered = finish_password_step(
                engine,
                settings,
                request.cookies.get(CHALLENGE_NAME),
                body.code.get_secret_value(),
                datetime.now(UTC),
                request.headers.get("user-agent", ""),
                reauthorize=lambda: validate_challenge(engine, request.cookies.get(CHALLENGE_NAME), "second_factor"),
            )
            notices(background, request, delivered)
            return issued_response(
                _view(issued.identity, request.app.state.recovery_mailer is not None), request, issued, background,
            )
        except FactorError as error:
            return factor_failure(error, request)
        except (ContentKeyUnavailable, ProtectedContentError):
            unavailable()

    @router.post("/sign-in/enrollment/start", response_model=EnrollmentView)
    def forced_start(request: Request):
        require_mutation_origin(request)
        try:
            result = start_forced_enrollment(
                engine, settings, request.cookies.get(CHALLENGE_NAME), datetime.now(UTC),
                reauthorize=lambda: validate_challenge(engine, request.cookies.get(CHALLENGE_NAME), "enrollment"),
            )
            view = EnrollmentView(**result.__dict__)
            payload = view.model_dump_json()
            actor = validate_challenge(engine, request.cookies.get(CHALLENGE_NAME), "enrollment")
            validate_enrollment(engine, actor, view.manual_key, view.expires_at, KeyRing.from_settings(settings))
            validate_challenge(engine, request.cookies.get(CHALLENGE_NAME), "enrollment")
            return Response(payload, media_type="application/json",
                            headers={"Cache-Control":"no-store", "Vary":"Cookie, Origin"})
        except FactorError as error:
            return factor_failure(error, request)
        except (ContentKeyUnavailable, ProtectedContentError):
            unavailable()

    @router.post("/sign-in/enrollment/confirm", response_model=ForcedEnrollmentView)
    def forced_confirm(
        body: FactorCodeRequest, request: Request, background: BackgroundTasks
    ):
        require_mutation_origin(request)
        try:
            issued, codes, delivered = finish_forced_enrollment(
                engine,
                settings,
                request.cookies.get(CHALLENGE_NAME),
                body.code.get_secret_value(),
                datetime.now(UTC),
                request.headers.get("user-agent", ""),
                reauthorize=lambda: validate_challenge(engine, request.cookies.get(CHALLENGE_NAME), "enrollment"),
            )
            notices(background, request, delivered)
            return issued_response(ForcedEnrollmentView(
                session=_view(issued.identity, request.app.state.recovery_mailer is not None),
                backup_codes=codes,
            ), request, issued, background)
        except FactorError as error:
            return factor_failure(error, request)
        except (ContentKeyUnavailable, ProtectedContentError):
            unavailable()

    @router.get("/sessions", response_model=list[DeviceView])
    def devices(request: Request, identity: Annotated[SessionIdentity, Depends(current_identity)]):
        def view(current):
            return [DeviceView(**row) for row in list_devices(
                engine, current.user_id, current.session_id, datetime.now(UTC),
            )]

        prepared = view(identity)

        def authorize(current):
            if view(current) != prepared:
                raise ApiError(409, "devices_changed", "Device sessions changed. Reload to continue.")

        return protected(prepared, request, identity, authorize)

    @router.post("/sessions/revoke-others", status_code=204)
    def others(
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        try:
            delivered = revoke_others(
                engine, identity.user_id, identity.session_id, datetime.now(UTC),
                reauthorize=lambda: current_identity(request),
            )
            notices(background, request, delivered)
            return Response(status_code=204, background=background)
        except FactorError as error:
            return factor_failure(error, request)

    @router.post("/sessions/{session_id}/revoke", status_code=204)
    def revoke(
        session_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        try:
            current = revoke_device(
                engine, identity.user_id, identity.session_id, session_id, datetime.now(UTC),
                reauthorize=lambda: current_identity(request),
            )
            response = Response(status_code=204)
            if current:
                clear_session_cookie(response, settings)
            return response
        except FactorError as error:
            return factor_failure(error, request)

    return router
