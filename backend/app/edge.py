"""Proxy-facing HTTPS redirects, client addresses, body limits, headers and access logs.

Host and the proxy protocol select an allowed HTTPS redirect; paths and queries are
preserved in that response. Access logs contain route templates, never request bodies,
query strings, credentials or cookies. The body limiter counts bytes without logging them.
"""

import ipaddress
import json
import logging
import time
from collections.abc import Iterable
from urllib.parse import quote, urlsplit

from starlette.datastructures import URL, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.contracts import ErrorResponse

ACCESS_LOGGER = logging.getLogger("app.access")
# The largest legitimate request is an 8 MiB import plus multipart framing.
MAX_REQUEST_BYTES = 9 * 1024 * 1024
TOO_LARGE_MESSAGE = "The request exceeds the 9 MiB upload limit."
_QUIET_PATHS = ("/api/v1/health/live", "/api/v1/health/ready")
_API_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_HTTP_METHODS = frozenset(
    ("GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH")
)
_DOCS_PATHS = ("/docs", "/docs/oauth2-redirect", "/redoc")


def _parse_address(value: str) -> str | None:
    candidate = value.strip().strip('"')
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1:
        candidate = candidate.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address)


def attempt_key(address: str) -> str:
    """Group IPv6 clients by /64, the smallest block a single subscriber usually controls."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(parsed, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False))
    return str(parsed)


def client_address(forwarded_for: Iterable[str], peer: str | None, trusted_hops: int) -> str:
    """Return the address seen by the first trusted proxy.

    Trusted proxies append the address they received a connection from, so with N trusted
    hops the client is the Nth entry from the right. Entries further left are supplied by the
    client and are never used. Without trusted hops, or when the chain is shorter than
    expected, the socket peer is used.
    """
    if trusted_hops > 0:
        entries = [item for header in forwarded_for for item in header.split(",")]
        if len(entries) >= trusted_hops:
            address = _parse_address(entries[-trusted_hops])
            if address:
                return address
    return peer or "unknown"


def scope_client_address(scope: Scope, trusted_hops: int) -> str:
    forwarded = [
        value.decode("latin-1")
        for name, value in scope.get("headers", ())
        if name == b"x-forwarded-for"
    ]
    client = scope.get("client")
    return client_address(forwarded, client[0] if client else None, trusted_hops)


def loggable_path(scope: Scope) -> str:
    """Only log server-defined route templates, never an unmatched request path."""
    template = getattr(scope.get("route"), "path", None)
    if isinstance(template, str):
        return template
    return "[unmatched]"


class ContentFreeErrorsMiddleware:
    """Keep unexpected exception text out of responses and the server traceback log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def recording_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        except Exception:  # noqa: BLE001 -- exception values may contain private content
            # An exception can carry parser content, SQL parameters or credentials.
            # No exception value or traceback is logged, even in development.
            logging.getLogger("app.errors").error("Request failed; internal error.")
            if started:
                raise RuntimeError("Response interrupted; internal error.") from None
            body = ErrorResponse(
                code="internal_error", message="The request could not be completed."
            )
            response = Response(
                body.model_dump_json(), status_code=500, media_type="application/json"
            )
            await response(scope, receive, send)


class RequestTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=413, detail="request_too_large")


def too_large_body() -> bytes:
    error = ErrorResponse(code="request_too_large", message=TOO_LARGE_MESSAGE)
    return json.dumps(error.model_dump()).encode("utf-8")


class RequestBodyLimitMiddleware:
    """Reject oversized bodies before parsing, including chunked bodies without a length."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = next(
            (value for name, value in scope.get("headers", ()) if name == b"content-length"),
            None,
        )
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            body = too_large_body()
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"connection", b"close"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestTooLarge()
            return message

        await self.app(scope, limited_receive, send)


async def request_too_large_handler(_request: Request, _exc: Exception) -> Response:
    return Response(
        too_large_body(),
        status_code=413,
        media_type="application/json",
        headers={"Connection": "close"},
    )


class HttpsRedirectMiddleware:
    """Redirect HTTP before any body or credentials are read behind the host proxy.

    The configured proxy must overwrite X-Forwarded-Proto. Host destinations come
    only from configured HTTPS origins, never Forwarded or X-Forwarded-Host.
    """

    def __init__(self, app: ASGIApp, *, allowed_origins: list[str]) -> None:
        self.app = app
        self.hosts = {
            urlsplit(origin).netloc.lower(): urlsplit(origin).netloc
            for origin in allowed_origins if urlsplit(origin).scheme == "https"
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("scheme") == "https":
            await self.app(scope, receive, send)
            return
        protocols = [value.strip().lower() for name, value in scope.get("headers", ())
                     if name == b"x-forwarded-proto"]
        if protocols == [b"https"]:
            await self.app(scope, receive, send)
            return
        # Docker's liveness check is local and has no router header. No other
        # route, method or network peer receives this exception.
        client = scope.get("client")
        if (not protocols and scope.get("method") in ("GET", "HEAD")
                and scope.get("path") == "/api/v1/health/live" and client
                and client[0] in ("127.0.0.1", "::1")):
            await self.app(scope, receive, send)
            return
        hosts = [value.decode("latin-1").lower() for name, value in scope.get("headers", ())
                 if name == b"host"]
        host = hosts[0].removesuffix(":80") if len(hosts) == 1 else ""
        destination = self.hosts.get(host)
        if destination is None:
            response = Response(status_code=400, headers={"Cache-Control": "no-store"})
        else:
            raw_path = scope.get("raw_path")
            path = raw_path.decode("ascii") if raw_path is not None else quote(scope["path"], safe="/")
            target = URL(scope=scope).replace(scheme="https", netloc=destination, path=path)
            response = RedirectResponse(str(target), status_code=307,
                                        headers={"Cache-Control": "no-store"})
        await response(scope, receive, send)


class SecurityHeadersMiddleware:
    """Hardening headers on every response, including CORS preflights and early errors.

    API responses are never cached. HSTS is only sent when the deployment is HTTPS.
    """

    def __init__(self, app: ASGIApp, *, strict_transport: bool) -> None:
        self.app = app
        self.strict_transport = strict_transport
        self.headers = [
            ("x-content-type-options", "nosniff"),
            ("referrer-policy", "no-referrer"),
            ("x-frame-options", "DENY"),
            # Only no-cors embedding (img/script) is refused; the website's CORS fetches pass.
            ("cross-origin-resource-policy", "same-origin"),
        ]
        if strict_transport:
            self.headers.append(
                ("strict-transport-security", "max-age=63072000; includeSubDomains")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        # Only actual development docs need their own scripts. Disabled production
        # docs and arbitrary paths beginning with /docs or /redoc keep the API policy.
        policy = self.strict_transport or path not in _DOCS_PATHS

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers:
                    headers.setdefault(name, value)
                if policy:
                    headers.setdefault("content-security-policy", _API_POLICY)
                if path.startswith("/api/"):
                    headers["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class AccessLogMiddleware:
    """One line per request: client, method, route template, status and duration."""

    def __init__(self, app: ASGIApp, *, trusted_proxy_hops: int) -> None:
        self.app = app
        self.trusted_proxy_hops = trusted_proxy_hops

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def recording_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        finally:
            path = scope.get("path", "")
            if not (status < 400 and path in _QUIET_PATHS):
                method = scope.get("method", "")
                if method not in _HTTP_METHODS:
                    method = "[unsupported]"
                ACCESS_LOGGER.info(
                    '%s "%s %s" %d %dms',
                    scope_client_address(scope, self.trusted_proxy_hops),
                    method,
                    loggable_path(scope),
                    status,
                    round((time.perf_counter() - started) * 1000),
                )


def configure_logging() -> None:
    """Send application logs, including the redacted access log, to standard error once."""
    logger = logging.getLogger("app")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
