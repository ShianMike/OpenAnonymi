"""Cookie session endpoints and reusable authentication dependencies."""

import hmac
import time
from collections import deque
from datetime import UTC, datetime
from threading import Lock
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.recovery import (
    InvalidRecoveryCode,
    RecoveryDeliveryError,
    complete_recovery,
    request_recovery,
)
from app.accounts.registration import AccountUnavailable, register_account
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
from app.config import Settings
from app.contracts import ErrorResponse, WorkspaceRole
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


class SessionView(BaseModel):
    user_id: UUID
    email: str
    expires_at: datetime
    csrf_token: str
    memberships: list[MembershipView]


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


def _view(identity: SessionIdentity) -> SessionView:
    return SessionView(
        user_id=identity.user_id,
        email=identity.email,
        expires_at=identity.expires_at,
        csrf_token=identity.csrf_token,
        memberships=[
            MembershipView(
                workspace_id=item.workspace_id,
                role=item.role,
                workspace_name=item.workspace_name,
            )
            for item in identity.memberships
        ],
    )


class AttemptLimiter:
    """Conservative per-process IP budget until deployment-wide limits are configured.

    State lives in this process only. Run exactly one worker and one instance; extra
    workers or replicas each get their own budget, and a restart resets it.
    """

    def __init__(self, maximum: int = 8, window_seconds: int = 300) -> None:
        self.maximum = maximum
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def take(self, client_ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._attempts) >= 10_000:
                self._attempts = {
                    key: values
                    for key, values in self._attempts.items()
                    if values and values[-1] > now - self.window_seconds
                }
                if len(self._attempts) >= 10_000 and client_ip not in self._attempts:
                    return False
            attempts = self._attempts.setdefault(client_ip, deque())
            while attempts and attempts[0] <= now - self.window_seconds:
                attempts.popleft()
            if len(attempts) >= self.maximum:
                return False
            attempts.append(now)
            return True


def request_client_ip(request: Request) -> str:
    """Attempt-limit key: the first trusted X-Forwarded-For hop, else the socket peer."""
    settings: Settings = request.app.state.settings
    return attempt_key(scope_client_address(request.scope, settings.trusted_proxy_hops))


def _session_cookie(value: str, *, max_age: int, settings: Settings) -> str:
    """Build the session cookie so issuing and clearing always use identical attributes.

    Production serves the website and the API from different sites, so the cookie must be
    SameSite=None and Secure. Partitioned (CHIPS) keys it to the website's top-level site,
    which keeps it usable where unpartitioned third-party cookies are blocked. Starlette
    only emits Partitioned on Python 3.14+, so the header is formatted here.
    """
    attributes = [f"{COOKIE_NAME}={value}", f"Max-Age={max_age}", f"Path={COOKIE_PATH}"]
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
    response.headers.append("set-cookie", _session_cookie(token, max_age=max_age, settings=settings))


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.headers.append("set-cookie", _session_cookie("", max_age=0, settings=settings))


def require_mutation_origin(request: Request) -> None:
    settings: Settings = request.app.state.settings
    if request.headers.get("origin") not in settings.allowed_origins:
        raise ApiError(403, "origin_denied", "This request origin is not allowed.")


def current_identity(request: Request) -> SessionIdentity:
    token = request.cookies.get(COOKIE_NAME)
    try:
        with Session(request.app.state.engine) as session:
            return read_session(session, token=token, now=datetime.now(UTC))
    except InvalidSession:
        raise ApiError(401, "sign_in_required", "Sign in to continue.") from None


def mutation_identity(request: Request) -> SessionIdentity:
    require_mutation_origin(request)
    identity = current_identity(request)
    supplied = request.headers.get("x-csrf-token", "")
    if len(supplied) > 200 or not hmac.compare_digest(supplied, identity.csrf_token):
        raise ApiError(403, "csrf_denied", "Refresh the session and try again.")
    return identity


def create_auth_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["accounts"])
    limiter = AttemptLimiter()
    registration_limiter = AttemptLimiter(maximum=3)
    recovery_request_limiter = AttemptLimiter(maximum=3)
    recovery_completion_limiter = AttemptLimiter()

    @router.post(
        "/sign-in",
        response_model=SessionView,
        responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def sign_in_route(body: SignInRequest, request: Request, response: Response) -> SessionView:
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
                )
        except InvalidCredentials:
            raise ApiError(
                401, "invalid_credentials", "Email or password was not accepted."
            ) from None
        set_session_cookie(response, issued.token, settings)
        return _view(issued.identity)

    @router.post(
        "/sign-up",
        status_code=201,
        response_model=SessionView,
        responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def sign_up_route(body: SignUpRequest, request: Request, response: Response) -> SessionView:
        require_mutation_origin(request)
        if not settings.registration_enabled:
            raise ApiError(
                403,
                "registration_closed",
                "Account creation is closed. Contact your workspace administrator.",
            )
        client_ip = request_client_ip(request)
        if not registration_limiter.take(client_ip):
            raise ApiError(
                429, "registration_limited", "Too many account creation attempts. Try again later."
            )
        try:
            with Session(engine) as session:
                issued = register_account(
                    session,
                    email=body.email,
                    password=body.password.get_secret_value(),
                    workspace_name=body.workspace_name,
                    now=datetime.now(UTC),
                )
        except AccountUnavailable:
            raise ApiError(
                409,
                "account_unavailable",
                "This account could not be created. Try signing in or recovering your account.",
            ) from None
        except ValueError as exc:
            raise ApiError(422, "invalid_registration", str(exc)) from None
        set_session_cookie(response, issued.token, settings)
        return _view(issued.identity)

    @router.get(
        "/session",
        response_model=SessionView,
        responses={401: {"model": ErrorResponse}},
    )
    def session_route(
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> SessionView:
        return _view(identity)

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
    def recovery_complete_route(body: RecoveryCompletion, request: Request) -> Response:
        require_mutation_origin(request)
        client_ip = request_client_ip(request)
        if not recovery_completion_limiter.take(client_ip):
            raise ApiError(429, "recovery_limited", "Too many recovery attempts. Try again later.")
        try:
            with Session(engine) as session:
                complete_recovery(
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
        return response

    return router
