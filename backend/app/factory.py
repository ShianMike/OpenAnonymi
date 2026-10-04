"""FastAPI application factory."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.admin_api import create_admin_router
from app.accounts.api import create_auth_router
from app.accounts.outbox import OutboxMailer
from app.accounts.recovery import RecoveryMailer, SmtpRecoveryMailer
from app.accounts.second_factor_api import create_second_factor_router
from app.batches.api import create_batch_router
from app.batches.worker import ScanWorker
from app.cleanup.api import create_cleanup_router
from app.cleanup.runner import periodic_cleanup
from app.comparison.api import create_comparison_router
from app.config import Settings, load_settings
from app.contracts import ErrorResponse, HealthResponse, ServiceMetadata, service_metadata
from app.custom_rules.api import create_custom_rules_router
from app.detection.api import create_detection_router
from app.edge import (
    AccessLogMiddleware,
    ContentFreeErrorsMiddleware,
    RequestBodyLimitMiddleware,
    RequestTooLarge,
    SecurityHeadersMiddleware,
    request_too_large_handler,
)
from app.errors import ApiError, api_error_handler, validation_error_handler
from app.exports.api import create_exports_router
from app.groups.api import create_groups_router
from app.intake.api import create_intake_router
from app.intake.import_api import create_import_router
from app.maintenance.api import create_maintenance_router
from app.recovery.api import create_recovery_router
from app.reviews.api import create_reviews_router
from app.team_review.api import create_team_router
from app.transformations.api import create_transform_router
from app.workspace.api import create_workspace_router
from app.workspace.presets_api import create_presets_router


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    recovery_mailer: RecoveryMailer | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    owned_engine = engine is None
    engine = engine or create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": settings.database_connect_timeout},
    )
    scan_worker = ScanWorker(engine, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if not settings.email_check_deliverability:
            logging.getLogger("app.accounts").warning("Email domain checks are disabled")
        cleanup_task = (
            asyncio.create_task(periodic_cleanup(engine))
            if settings.environment != "test"
            else None
        )
        scan_task = (
            asyncio.create_task(scan_worker.run()) if settings.environment != "test" else None
        )
        try:
            yield
        finally:
            if scan_task is not None:
                scan_task.cancel()
                with suppress(asyncio.CancelledError):
                    await scan_task
            if cleanup_task is not None:
                cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await cleanup_task
            if owned_engine:
                engine.dispose()

    production = settings.environment == "production"
    # Interactive docs and the public schema are development aids only.
    docs = {} if not production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    # TLS terminates at the host proxy. A slash redirect would otherwise use the
    # internal HTTP scheme, potentially resending a request body to an insecure URL.
    app = FastAPI(
        title="OpenAnonymi API",
        version="0.1.0",
        lifespan=lifespan,
        redirect_slashes=not production,
        **docs,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.scan_worker = scan_worker
    app.state.recovery_mailer = recovery_mailer or (
        SmtpRecoveryMailer(settings)
        if settings.smtp_host
        else OutboxMailer(settings.dev_mail_outbox)
        if settings.dev_mail_outbox
        else None
    )
    # Added innermost first. The body limit sits inside CORS so a 413 still carries CORS
    # headers the website can read; security headers and the access log wrap everything.
    app.add_middleware(ContentFreeErrorsMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        expose_headers=["X-CSV-Prefixed-Cells"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, strict_transport=production)
    app.add_middleware(AccessLogMiddleware, trusted_proxy_hops=settings.trusted_proxy_hops)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(RequestTooLarge, request_too_large_handler)
    app.include_router(create_auth_router(engine, settings))
    app.include_router(create_second_factor_router(engine, settings))
    app.include_router(create_admin_router(engine))
    app.include_router(create_intake_router(engine))
    app.include_router(create_import_router(engine))
    app.include_router(create_batch_router(engine))
    app.include_router(create_comparison_router(engine))
    app.include_router(create_team_router(engine))
    app.include_router(create_recovery_router(engine))
    app.include_router(create_custom_rules_router(engine))
    app.include_router(create_detection_router(engine))
    app.include_router(create_groups_router(engine))
    app.include_router(create_transform_router(engine))
    app.include_router(create_reviews_router(engine))
    app.include_router(create_exports_router(engine))
    app.include_router(create_workspace_router(engine))
    app.include_router(create_presets_router(engine))
    app.include_router(create_cleanup_router(engine))
    app.include_router(create_maintenance_router(engine, settings))

    @app.get("/api/v1/health/live", response_model=HealthResponse)
    def live() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/api/v1/health/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
    )
    def ready(response: Response) -> HealthResponse:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            response.status_code = 503
            return HealthResponse(status="unavailable")
        return HealthResponse(status="ok")

    @app.get(
        "/api/v1/meta",
        response_model=ServiceMetadata,
        responses={422: {"model": ErrorResponse}},
    )
    def metadata() -> ServiceMetadata:
        return service_metadata()

    return app
