"""Serve the compiled website after API routes, with safe client-route fallback."""

from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class FrontendFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        # StaticFiles uses the host's path separator, including backslashes on Windows.
        parts = PurePosixPath(path.replace("\\", "/")).parts
        if any(part.startswith(".") for part in parts) or (
            parts and parts[0] in {"api", "docs", "redoc", "openapi.json"}
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
