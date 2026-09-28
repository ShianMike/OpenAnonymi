"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.admin_api import create_admin_router
from app.accounts.api import create_auth_router
from app.accounts.recovery import RecoveryMailer, SmtpRecoveryMailer
from app.config import Settings, load_settings
from app.contracts import ErrorResponse, HealthResponse, ServiceMetadata, service_metadata
from app.detection.api import create_detection_router
from app.errors import ApiError, api_error_handler, validation_error_handler
from app.exports.api import create_exports_router
from app.groups.api import create_groups_router
from app.intake.api import create_intake_router
from app.reviews.api import create_reviews_router
from app.transformations.api import create_transform_router


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
        connect_args={"connect_timeout": 2},
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if owned_engine:
            engine.dispose()

    app = FastAPI(title="OpenAnonymi API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.recovery_mailer = recovery_mailer or (
        SmtpRecoveryMailer(settings) if settings.smtp_host else None
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(create_auth_router(engine, settings))
    app.include_router(create_admin_router(engine))
    app.include_router(create_intake_router(engine))
    app.include_router(create_detection_router(engine))
    app.include_router(create_groups_router(engine))
    app.include_router(create_transform_router(engine))
    app.include_router(create_reviews_router(engine))
    app.include_router(create_exports_router(engine))

    @app.middleware("http")
    async def prevent_api_caching(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

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
