"""ASGI entry point. Run from the backend directory with configured environment.

Serve with exactly one Uvicorn worker: attempt limits and review undo are process-local.
"""

from app.edge import configure_logging
from app.factory import create_app

configure_logging()
app = create_app()
