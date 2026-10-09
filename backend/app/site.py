"""Serve the compiled website after API routes, with safe client-route fallback."""

from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.routing import Match, Mount
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

RESERVED_PATHS = {"api", "docs", "redoc", "openapi.json"}


class FrontendMount(Mount):
    def matches(self, scope: Scope):
        # A catch-all Mount would claim API requests whose method did not match,
        # replacing the API's 405 with a static-file 404.
        if scope["path"].lstrip("/").split("/", 1)[0] in RESERVED_PATHS:
            return Match.NONE, {}
        return super().matches(scope)


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        # StaticFiles uses the host's path separator, including backslashes on Windows.
        parts = PurePosixPath(path.replace("\\", "/")).parts
        if any(part.startswith(".") for part in parts) or (
            parts and parts[0] in RESERVED_PATHS
        ):
            raise HTTPException(404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or PurePosixPath(path).suffix or (
                parts and parts[0] == "assets"
            ):
                raise
            path = "index.html"
            response = await super().get_response(path, scope)
        # Vite's index.html supplies the full policy. frame-ancestors requires a header.
        response.headers["content-security-policy"] = "frame-ancestors 'none'"
        response.headers["cache-control"] = (
            "no-store" if not PurePosixPath(path).suffix or path.endswith(".html") else "no-cache"
        )
        return response
