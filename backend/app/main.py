"""ASGI entry point. Run from the backend directory with configured environment.

Serve with one Uvicorn worker for model memory; limits and undo are in PostgreSQL.
"""

from pathlib import Path

from app.edge import configure_logging
from app.factory import create_app
from app.site import FrontendFiles, FrontendMount

configure_logging()
app = create_app()

# The production image includes this compiled directory; local API development
# keeps using Vite. Mount last so /api/v1 contracts and lifespan stay unchanged.
frontend = Path(__file__).resolve().parent.parent / "frontend"
if frontend.is_dir():
    app.router.routes.append(FrontendMount(
        "/", app=FrontendFiles(directory=frontend, html=True), name="website",
    ))
