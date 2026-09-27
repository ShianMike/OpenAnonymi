"""Stable, content-free application errors."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.contracts import ErrorDetail, ErrorResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's raw error includes `input`, which may be document text. Never return it.
    details = [
        ErrorDetail(
            field=".".join(str(part) for part in item["loc"]),
            issue=str(item["type"]),
        )
        for item in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code="validation_error", message="Check the submitted fields.", details=details
        ).model_dump(),
    )
