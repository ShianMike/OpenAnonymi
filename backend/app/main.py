"""ASGI entry point. Run from the backend directory with configured environment.

Serve with one Uvicorn worker for model memory; limits and undo are in PostgreSQL.
"""

from app.edge import configure_logging
from app.factory import create_app

configure_logging()
app = create_app()
