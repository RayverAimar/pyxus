"""Starlette application for the Pyxus web UI.

Creates an ASGI application that serves both the REST API endpoints
and the pre-built React frontend as static files. The graph is loaded
once at startup and shared across all requests via app state.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from pyxus.graph.store import GraphStore
from pyxus.web.routes import make_routes

__all__ = ["create_app"]

logger = logging.getLogger("pyxus")

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    graph: GraphStore,
    metadata: dict[str, Any] | None = None,
    dev: bool = False,
) -> Starlette:
    """Build the Starlette ASGI application.

    Args:
        graph: The loaded knowledge graph to serve.
        metadata: Index metadata (indexed_at, call_resolution_rate, etc.).
        dev: When True, skip mounting static files (Vite dev server handles them).
    """
    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET"],
            allow_headers=["*"],
        ),
    ]

    routes = make_routes()

    if not dev and _STATIC_DIR.is_dir() and any(_STATIC_DIR.iterdir()):
        routes.append(
            Mount("/", app=StaticFiles(directory=str(_STATIC_DIR), html=True), name="static"),
        )
    elif not dev:
        logger.warning("No static files found at %s. Run the frontend build first.", _STATIC_DIR)

    app = Starlette(routes=routes, middleware=middleware)
    app.state.graph = graph
    app.state.metadata = metadata

    return app
