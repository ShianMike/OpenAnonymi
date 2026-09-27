"""ASGI entry point. Run from the backend directory with configured environment."""

from app.factory import create_app

app = create_app()
