"""HTTP API routes for the Pyxus web UI.

Thin wrapper around the graph query functions, exposing them as JSON
endpoints that the React frontend consumes. Each route loads the graph
from the shared application state and delegates to the appropriate
query function.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from pyxus.graph.queries import context as _context
from pyxus.graph.queries import impact as _impact
from pyxus.graph.queries import imports as _imports
from pyxus.graph.queries import query as _query
from pyxus.graph.store import GraphStore
from pyxus.web.serializers import serialize_graph, serialize_module_graph

__all__ = ["make_routes"]


def _get_graph(request: Request) -> GraphStore:
    """Retrieve the GraphStore instance from Starlette app state."""
    return request.app.state.graph


def _get_metadata(request: Request) -> dict[str, Any]:
    """Retrieve the index metadata from Starlette app state."""
    return request.app.state.metadata or {}


async def graph_endpoint(request: Request) -> JSONResponse:
    """Return the full graph or a filtered view for the frontend."""
    graph = _get_graph(request)
    level = request.query_params.get("level")

    if level == "module":
        data = serialize_module_graph(graph)
    else:
        metadata = _get_metadata(request)
        data = serialize_graph(graph, metadata=metadata)

    return JSONResponse(data)


async def context_endpoint(request: Request) -> JSONResponse:
    """Return 360-degree context for a symbol by name."""
    graph = _get_graph(request)
    name = request.path_params["name"]
    result = _context(graph, name)
    return JSONResponse(result)


async def impact_endpoint(request: Request) -> JSONResponse:
    """Return blast radius analysis for a symbol."""
    graph = _get_graph(request)
    name = request.path_params["name"]
    direction = request.query_params.get("direction", "upstream")
    max_depth = int(request.query_params.get("max_depth", "3"))
    result = _impact(graph, name, direction=direction, max_depth=max_depth)
    # RiskLevel is a StrEnum — convert to plain string for JSON serialization
    if "risk" in result:
        result["risk"] = str(result["risk"])
    return JSONResponse(result)


async def search_endpoint(request: Request) -> JSONResponse:
    """Search symbols by name substring."""
    graph = _get_graph(request)
    q = request.query_params.get("q", "")
    limit = int(request.query_params.get("limit", "10"))
    if not q:
        return JSONResponse({"query": "", "total_matches": 0, "results": []})
    result = _query(graph, q, limit=limit)
    return JSONResponse(result)


async def imports_endpoint(request: Request) -> JSONResponse:
    """Return module-level import dependencies and circular imports."""
    graph = _get_graph(request)
    result = _imports(graph)
    return JSONResponse(result)


async def status_endpoint(request: Request) -> JSONResponse:
    """Return index metadata: freshness, counts, resolution rate."""
    metadata = _get_metadata(request)
    graph = _get_graph(request)
    data = {
        **metadata,
        "symbol_count": graph.node_count,
        "edge_count": graph.edge_count,
    }
    return JSONResponse(data)


def make_routes() -> list[Route]:
    """Build the list of API routes for the Starlette application."""
    return [
        Route("/api/graph", graph_endpoint),
        Route("/api/context/{name:path}", context_endpoint),
        Route("/api/impact/{name:path}", impact_endpoint),
        Route("/api/search", search_endpoint),
        Route("/api/imports", imports_endpoint),
        Route("/api/status", status_endpoint),
    ]
