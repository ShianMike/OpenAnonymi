"""Cookie session endpoints and reusable authentication dependencies."""

import hmac
import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.challenges import CHALLENGE_NAME, CHALLENGE_PATH, CHALLENGE_TTL, IssuedChallenge
from app.accounts.email_rules import EmailRuleError, lookup_forms
from app.accounts.limits import AttemptLimiter
from app.accounts.recovery import (
    InvalidRecoveryCode,
    RecoveryDeliveryError,
    complete_recovery,
    request_recovery,
)
from app.accounts.security import (
    COOKIE_NAME,
    COOKIE_PATH,
    SESSION_TTL,
    InvalidCredentials,
    InvalidSession,
    SessionIdentity,
    change_password,
    read_session,
    revoke_session,
    sign_in,
)
from app.accounts.security_notices import SecurityNotice, deliver_notice
from app.accounts.signup import (
    AccountUnavailable,
    CodeDelivery,
    InvalidEmailVerificationCode,
    InvalidRegistrationCode,
    confirm_email_verification,
    request_email_verification,
    request_registration,
    verify_registration,
)
from app.config import Settings
from app.contracts import ErrorResponse, WorkspaceRole
from app.db.crypto import ContentKeyUnavailable, ProtectedContentError
from app.edge import attempt_key, scope_client_address
from app.errors import ApiError


class SignInRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)


class SignUpRequest(BaseModel):
    model_config = {"extra": "forbid"}
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=12, max_length=1024)
    workspace_name: str = Field(min_length=1, max_length=120)


class MembershipView(BaseModel):
    workspace_id: UUID
    role: WorkspaceRole
    workspace_name: str
    require_second_factor: bool = False


class SessionView(BaseModel):
    user_id: UUID
    email: str
    expires_at: datetime
    csrf_token: str
    memberships: list[MembershipView]
    email_verified: bool = False
    email_verification_available: bool = False
    second_factor_enabled: bool = False
    second_factor_setup_required: bool = False
    security_emails_available: bool = False


class ChallengeView(BaseModel):
    status: Literal["second_factor_required", "enrollment_required"]
    expires_at: datetime


class RegistrationMessage(BaseModel):
    message: str
    expires_in_seconds: int = 900


class EmailProofCode(BaseModel):
    code: SecretStr = Field(min_length=1, max_length=200)

    @field_validator("code")
    @classmethod
    def validate_email_code(cls, value: SecretStr) -> SecretStr:
        code = value.get_secret_value().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32}", code):
            raise ValueError("Enter the complete email code.")
        return SecretStr(code)


class RegistrationVerification(EmailProofCode):
    model_config = {"extra": "forbid"}
    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)


class RecoveryRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)


class RecoveryCompletion(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    code: str = Field(min_length=1, max_length=200)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class RecoveryMessage(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


def _view(identity: SessionIdentity, mail_available: bool = False) -> SessionView:
    return SessionView(
        user_id=identity.user_id,
        email=identity.email,
        expires_at=identity.expires_at,
        csrf_token=identity.csrf_token,
        email_verified=identity.email_verified,
        email_verification_available=mail_available,
        second_factor_enabled=identity.second_factor_enabled,
        second_factor_setup_required=identity.second_factor_setup_required,
        security_emails_available=mail_available,
        memberships=[
            MembershipView(
                workspace_id=item.workspace_id,
                role=item.role,
                workspace_name=item.workspace_name,
                require_second_factor=item.require_second_factor,
            )
            for item in identity.memberships
        ],
    )


def request_client_ip(request: Request) -> str:
    """Attempt-limit key: the first trusted X-Forwarded-For hop, else the socket peer."""
    settings: Settings = request.app.state.settings
    return attempt_key(scope_client_address(request.scope, settings.trusted_proxy_hops))


def _cookie(name: str, value: str, *, path: str, max_age: int, settings: Settings) -> str:
    """Build the session cookie so issuing and clearing always use identical attributes.

    Production serves the website and the API from different sites, so the cookie must be
    SameSite=None and Secure. Partitioned (CHIPS) keys it to the website's top-level site,
    which keeps it usable where unpartitioned third-party cookies are blocked. Starlette
    only emits Partitioned on Python 3.14+, so the header is formatted here.
    """
    attributes = [f"{name}={value}", f"Max-Age={max_age}", f"Path={path}"]
    if max_age == 0:
        attributes.append("Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    attributes.append("HttpOnly")
    if settings.environment == "production":
        attributes.extend(("Secure", "SameSite=None", "Partitioned"))
    else:
        attributes.append("SameSite=Lax")
    return "; ".join(attributes)


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    max_age = int(SESSION_TTL.total_seconds())
    response.headers.append(
        "set-cookie",
        _cookie(COOKIE_NAME, token, path=COOKIE_PATH, max_age=max_age, settings=settings),
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.headers.append(
        "set-cookie", _cookie(COOKIE_NAME, "", path=COOKIE_PATH, max_age=0, settings=settings)
    )


def set_challenge_cookie(response: Response, token: str, settings: Settings) -> None:
    response.headers.append(
        "set-cookie",
        _cookie(
            CHALLENGE_NAME,
            token,
            path=CHALLENGE_PATH,
            max_age=int(CHALLENGE_TTL.total_seconds()),
            settings=settings,
        ),
    )


def clear_challenge_cookie(response: Response, settings: Settings) -> None:
    response.headers.append(
        "set-cookie", _cookie(CHALLENGE_NAME, "", path=CHALLENGE_PATH, max_age=0, settings=settings)
    )


def require_mutation_origin(request: Request) -> None:
    settings: Settings = request.app.state.settings
    if request.headers.get("origin") not in settings.allowed_origins:
        raise ApiError(403, "origin_denied", "This request origin is not allowed.")


def current_identity(request: Request) -> SessionIdentity:
    token = request.cookies.get(COOKIE_NAME)
    try:
        with Session(request.app.state.engine) as session:
            identity = read_session(session, token=token, now=datetime.now(UTC))
            session.commit()
            return identity
    except InvalidSession:
        raise ApiError(401, "sign_in_required", "Sign in to continue.") from None


def mutation_identity(request: Request) -> SessionIdentity:
    require_mutation_origin(request)
    identity = current_identity(request)
    supplied = request.headers.get("x-csrf-token", "")
    if (
        len(supplied) != len(identity.csrf_token)
        or not supplied.isascii()
        or not hmac.compare_digest(supplied, identity.csrf_token)
    ):
        raise ApiError(403, "csrf_denied", "Refresh the session and try again.")
    return identity


def create_auth_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["accounts"])
    limiter = AttemptLimiter(engine, settings, scope="sign_in")
    registration_limiter = AttemptLimiter(engine, settings, scope="registration", maximum=3)
    registration_verify_limiter = AttemptLimiter(engine, settings, scope="registration_verify")
    registration_verify_address = AttemptLimiter(
        engine,
        settings,
        scope="registration_verify_address",
        maximum=10,
        window_seconds=900,
        network_scope=False,
    )
    email_verification_limiter = AttemptLimiter(
        engine,
        settings,
        scope="email_verification_request",
        maximum=3,
        window_seconds=3600,
        network_scope=False,
    )
    recovery_request_limiter = AttemptLimiter(engine, settings, scope="recovery_request", maximum=3)
    recovery_completion_limiter = AttemptLimiter(engine, settings, scope="recovery_complete")

    @router.post(
        "/sign-in",
        response_model=SessionView | ChallengeView,
        responses={
            202: {"model": ChallengeView},
            401: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def sign_in_route(
        body: SignInRequest, request: Request, response: Response
    ) -> SessionView | ChallengeView:
        require_mutation_origin(request)
        client_ip = request_client_ip(request)
        if not limiter.take(client_ip):
            raise ApiError(429, "sign_in_limited", "Too many sign-in attempts. Try again later.")
        try:
            with Session(engine) as session:
                issued = sign_in(
                    session,
                    email=body.email,
                    password=body.password.get_secret_value(),
                    now=datetime.now(UTC),
                    user_agent=request.headers.get("user-agent", ""),
                )
        except InvalidCredentials:
            raise ApiError(
                401, "invalid_credentials", "Email or password was not accepted."
            ) from None
        if isinstance(issued, IssuedChallenge):
            response.status_code = 202
            clear_session_cookie(response, settings)
            set_challenge_cookie(response, issued.token, settings)
            return ChallengeView(status=issued.status, expires_at=issued.expires_at)
        set_session_cookie(response, issued.token, settings)
        clear_challenge_cookie(response, settings)
        return _view(issued.identity, request.app.state.recovery_mailer is not None)

    def dispatch(mailer, delivery: CodeDelivery, method: str, event: str):
        try:
            getattr(mailer, method)(delivery.recipient, delivery.code)
        except RecoveryDeliveryError:
            logging.getLogger("app.accounts").warning(event)

    @router.post(
        "/sign-up",
        status_code=202,
        response_model=RegistrationMessage,
        responses={
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def sign_up_route(
        body: SignUpRequest, request: Request, background: BackgroundTasks
    ) -> RegistrationMessage:
        require_mutation_origin(request)
        if not settings.registration_enabled:
            raise ApiError(
                403,
                "registration_closed",
                "Account creation is closed. Contact your workspace administrator.",
            )
        mailer = request.app.state.recovery_mailer
        if mailer is None or not settings.active_key_id:
            raise ApiError(
                503,
                "registration_unavailable",
                "Self-registration isn't available on this site right now. Ask a workspace administrator for an invitation.",
            )
        if not registration_limiter.take(request_client_ip(request)):
            raise ApiError(
                429, "registration_limited", "Too many account creation attempts. Try again later."
            )
        try:
            delivery = request_registration(
                engine,
                settings=settings,
                email=body.email,
                password=body.password.get_secret_value(),
                workspace_name=body.workspace_name,
                now=datetime.now(UTC),
            )
        except EmailRuleError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from None
        except ValueError as exc:
            raise ApiError(422, "invalid_registration", str(exc)) from None
        if delivery:
            background.add_task(
                dispatch,
                mailer,
                delivery,
                "send_registration_code",
                "registration_code_delivery_failed",
            )
        return RegistrationMessage(
            message="If this address can be used, we sent a code to it. It expires in 15 minutes."
        )

    @router.post(
        "/sign-up/verify",
        status_code=201,
        response_model=SessionView,
        responses={
            400: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def verify_sign_up_route(
        body: RegistrationVerification, request: Request, response: Response
    ) -> SessionView:
        require_mutation_origin(request)
        try:
            subject = lookup_forms(body.email)[0]
        except ValueError:
            subject = "invalid"
        if not registration_verify_limiter.take(
            request_client_ip(request)
        ) or not registration_verify_address.take(subject):
            raise ApiError(
                429,
                "registration_verify_limited",
                "Too many verification attempts. Try again later.",
            )
        try:
            issued = verify_registration(
                engine,
                settings=settings,
                email=body.email,
                code=body.code.get_secret_value(),
                password=body.password.get_secret_value(),
                now=datetime.now(UTC),
                user_agent=request.headers.get("user-agent", ""),
            )
        except InvalidRegistrationCode:
            raise ApiError(
                400,
                "invalid_registration_code",
                "That code and password don't match a pending sign-up.",
            ) from None
        except AccountUnavailable:
            raise ApiError(
                409,
                "account_unavailable",
                "This account could not be created. Try signing in or recovering your account.",
            ) from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(
                503, "registration_unavailable", "Self-registration is unavailable right now."
            ) from None
        set_session_cookie(response, issued.token, settings)
        return _view(issued.identity, request.app.state.recovery_mailer is not None)

    @router.post("/email-verification", status_code=202, response_model=RegistrationMessage)
    def request_email_proof_route(
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> RegistrationMessage:
        mailer = request.app.state.recovery_mailer
        if mailer is None:
            raise ApiError(
                503,
                "email_verification_unavailable",
                "Email verification is unavailable right now.",
            )
        if not email_verification_limiter.take(str(identity.user_id)):
            raise ApiError(
                429, "email_verification_limited", "Too many code requests. Try again later."
            )
        try:
            delivery = request_email_verification(
                engine, user_id=identity.user_id, now=datetime.now(UTC)
            )
        except InvalidSession:
            raise ApiError(401, "sign_in_required", "Sign in to continue.") from None
        if delivery:
            background.add_task(
                dispatch,
                mailer,
                delivery,
                "send_email_verification_code",
                "email_verification_delivery_failed",
            )
        return RegistrationMessage(
            message="If verification is needed, we sent you a code. It expires in 15 minutes."
        )

    @router.post("/email-verification/confirm", status_code=204)
    def confirm_email_proof_route(
        body: EmailProofCode, identity: Annotated[SessionIdentity, Depends(mutation_identity)]
    ) -> Response:
        try:
            confirm_email_verification(
                engine,
                user_id=identity.user_id,
                code=body.code.get_secret_value(),
                now=datetime.now(UTC),
            )
        except InvalidEmailVerificationCode:
            raise ApiError(
                400,
                "invalid_verification_code",
                "That code is invalid or expired. Request a new code.",
            ) from None
        except InvalidSession:
            raise ApiError(401, "sign_in_required", "Sign in to continue.") from None
        return Response(status_code=204)

    @router.get(
        "/session",
        response_model=SessionView,
        responses={401: {"model": ErrorResponse}},
    )
    def session_route(
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> SessionView:
        return _view(identity, request.app.state.recovery_mailer is not None)

    @router.post(
        "/sign-out",
        status_code=204,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    )
    def sign_out_route(
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> Response:
        with Session(engine) as session:
            try:
                revoke_session(session, identity=identity, now=datetime.now(UTC))
            except InvalidSession:
                raise ApiError(401, "sign_in_required", "Sign in to continue.") from None
        response = Response(status_code=204)
        clear_session_cookie(response, settings)
        return response

    @router.post(
        "/change-password",
        status_code=204,
        responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def change_password_route(
        body: ChangePasswordRequest,
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> Response:
        try:
            with Session(engine) as session:
                change_password(
                    session,
                    identity=identity,
                    current_password=body.current_password.get_secret_value(),
                    new_password=body.new_password.get_secret_value(),
                    now=datetime.now(UTC),
                )
        except InvalidCredentials:
            raise ApiError(
                400, "incorrect_password", "Current password was not accepted."
            ) from None
        except ValueError as exc:
            raise ApiError(422, "invalid_password", str(exc)) from None
        response = Response(status_code=204)
        clear_session_cookie(response, settings)
        background.add_task(
            deliver_notice,
            request.app.state.recovery_mailer,
            SecurityNotice(identity.email, "password_changed", datetime.now(UTC)),
        )
        response.background = background
        return response

    @router.post(
        "/recovery/request",
        status_code=202,
        response_model=RecoveryMessage,
        responses={503: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def recovery_request_route(body: RecoveryRequest, request: Request) -> RecoveryMessage:
        require_mutation_origin(request)
        mailer = request.app.state.recovery_mailer
        if mailer is None:
            raise ApiError(503, "recovery_unavailable", "Account recovery is not configured.")
        client_ip = request_client_ip(request)
        if not recovery_request_limiter.take(client_ip):
            raise ApiError(429, "recovery_limited", "Too many recovery requests. Try again later.")
        try:
            with Session(engine) as session:
                request_recovery(session, email=body.email, now=datetime.now(UTC), mailer=mailer)
        except RecoveryDeliveryError:
            raise ApiError(
                503, "recovery_delivery_failed", "Recovery email could not be sent."
            ) from None
        return RecoveryMessage(message="If this account can be recovered, a code has been sent.")

    @router.post(
        "/recovery/complete",
        status_code=204,
        responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def recovery_complete_route(
        body: RecoveryCompletion, request: Request, background: BackgroundTasks
    ) -> Response:
        require_mutation_origin(request)
        client_ip = request_client_ip(request)
        if not recovery_completion_limiter.take(client_ip):
            raise ApiError(429, "recovery_limited", "Too many recovery attempts. Try again later.")
        try:
            with Session(engine) as session:
                recipient = complete_recovery(
                    session,
                    email=body.email,
                    code=body.code,
                    new_password=body.new_password.get_secret_value(),
                    now=datetime.now(UTC),
                )
        except InvalidRecoveryCode:
            raise ApiError(
                400, "invalid_recovery_code", "The recovery code is invalid or expired."
            ) from None
        response = Response(status_code=204)
        clear_session_cookie(response, settings)
        clear_challenge_cookie(response, settings)
        background.add_task(
            deliver_notice,
            request.app.state.recovery_mailer,
            SecurityNotice(recipient, "password_changed", datetime.now(UTC)),
        )
        response.background = background
        return response

    return router
