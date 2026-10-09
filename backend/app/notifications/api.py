from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.engine import Engine

from app.accounts.api import current_identity, mutation_identity
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.contracts import ErrorResponse
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.errors import ApiError
from app.notifications.contracts import (
    NotificationPage,
    NotificationPreferences,
    ReadAllResult,
    UnreadCount,
    UpdateNotificationPreferences,
)
from app.notifications.service import (
    NotificationNotFound,
    NotificationPreferenceUnavailable,
    NotificationReadChanged,
    list_notifications,
    mark_all_read,
    mark_read,
    preferences,
    unread_count,
    update_preferences,
    validate_notification_page,
)


def guarded(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except NotificationNotFound:
        raise ApiError(404, "notification_not_found", "Notification not found.") from None
    except NotificationReadChanged:
        raise ApiError(409, "notifications_changed", "Notifications changed while loading. Retry.") from None
    except NotificationPreferenceUnavailable:
        raise ApiError(
            503, "notification_emails_unavailable", "Notification email is not configured."
        ) from None
    except (ContentKeyUnavailable, ProtectedContentError):
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None


def create_notifications_router(engine: Engine):
    router = APIRouter(prefix="/api/v1", tags=["notifications"])

    @router.get(
        "/notifications", response_model=NotificationPage,
        responses={code: {"model": ErrorResponse} for code in (401, 404, 409, 503)},
    )
    def list_route(
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
        cursor: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 50,
    ):
        def load():
            return list_notifications(
                engine,
                identity.user_id,
                KeyRing.from_settings(request.app.state.settings),
                datetime.now(UTC),
                cursor,
                limit,
            )

        view = guarded(load)
        return protected_json_response(view, request, identity, lambda current: guarded(
            validate_notification_page, engine, current.user_id, view, datetime.now(UTC)
        ))

    @router.get("/notifications/unread-count", response_model=UnreadCount)
    def unread_route(identity: Annotated[SessionIdentity, Depends(current_identity)]):
        return UnreadCount(count=unread_count(engine, identity.user_id, datetime.now(UTC)))

    @router.post("/notifications/read-all", response_model=ReadAllResult)
    def read_all_route(identity: Annotated[SessionIdentity, Depends(mutation_identity)]):
        return ReadAllResult(changed=mark_all_read(engine, identity.user_id, datetime.now(UTC)))

    @router.post("/notifications/{notification_id}/read", status_code=204)
    def read_route(
        notification_id: UUID, identity: Annotated[SessionIdentity, Depends(mutation_identity)]
    ):
        guarded(mark_read, engine, notification_id, identity.user_id, datetime.now(UTC))
        return Response(status_code=204)

    @router.get("/auth/preferences", response_model=NotificationPreferences)
    def preferences_route(
        request: Request, identity: Annotated[SessionIdentity, Depends(current_identity)]
    ):
        return guarded(
            preferences, engine, identity.user_id, request.app.state.recovery_mailer is not None
        )

    @router.put("/auth/preferences", response_model=NotificationPreferences)
    def update_route(
        body: UpdateNotificationPreferences,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        return guarded(
            update_preferences,
            engine,
            identity.user_id,
            body.notification_emails,
            request.app.state.recovery_mailer is not None,
        )

    return router
