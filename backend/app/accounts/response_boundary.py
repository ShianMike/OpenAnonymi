"""Serialize protected JSON before fresh session and resource authorization."""

from collections.abc import Callable

from fastapi import Request, Response
from pydantic import BaseModel

from app.accounts.api import _token_identity, current_identity
from app.accounts.security import SessionIdentity
from app.errors import ApiError


def _same_session(request: Request, expected: SessionIdentity, token: str | None = None) -> SessionIdentity:
    current = current_identity(request) if token is None else _token_identity(request, token)
    if current.session_id != expected.session_id or current.user_id != expected.user_id:
        raise ApiError(401, "sign_in_required", "Sign in to continue.")
    return current


def protected_json_response(
    view: BaseModel | list[BaseModel],
    request: Request,
    identity: SessionIdentity,
    authorize: Callable[[SessionIdentity], None],
    *,
    status_code: int = 200,
    token: str | None = None,
) -> Response:
    payload = (
        b"[" + b",".join(item.model_dump_json().encode("utf-8") for item in view) + b"]"
        if isinstance(view, list) else view.model_dump_json().encode("utf-8")
    )
    authorize(_same_session(request, identity, token))
    # Resource checks can involve several current rows. A session that ends
    # during those checks must not release the already serialized private body.
    _same_session(request, identity, token)
    return Response(
        payload,
        status_code=status_code,
        media_type="application/json",
        headers={"Cache-Control": "no-store", "Vary": "Cookie, Origin"},
    )
