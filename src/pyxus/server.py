"""MCP server exposing the Pyxus knowledge graph via FastMCP.

Provides three tools that AI agents can use to understand Python codebases:
- context: 360-degree view of any symbol
- impact: blast radius analysis
- search: find symbols by name

The server loads the graph from .pyxus/graph.pkl on startup. If no index
exists, tools return a helpful error message directing users to run
``pyxus analyze`` first.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastmcp import FastMCP

from pyxus.graph.persistence import get_index_metadata, load_graph
from pyxus.graph.queries import context as _context
from pyxus.graph.queries import impact as _impact
from pyxus.graph.queries import query as _query
from pyxus.graph.store import GraphStore

mcp = FastMCP("pyxus")

# The graph is loaded lazily on first tool call and cached for the session
_graph_cache: GraphStore | None = None
_repo_path: str | None = None


def _find_repo_root() -> str:
    """Find the repository root by searching upward for .pyxus/ or .git/.

    Starts from the current working directory and walks up the directory
    tree. Falls back to cwd if neither marker is found.
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".pyxus").is_dir() or (parent / ".git").is_dir():
            return str(parent)
    return str(cwd)


def _get_graph() -> GraphStore | None:
    """Load the graph from disk, caching it for subsequent tool calls."""
    global _graph_cache, _repo_path
    if _graph_cache is not None:
        return _graph_cache

    _repo_path = os.environ.get("PYXUS_REPO_PATH") or _find_repo_root()
    _graph_cache = load_graph(_repo_path)
    return _graph_cache


def _no_index_error() -> str:
    """Helpful error message when no index exists."""
    return json.dumps(
        {
            "error": "No Pyxus index found. Run `pyxus analyze` first to index your codebase.",
        }
    )


@mcp.tool()
def context(name: str) -> str:
    """Get a 360-degree view of a symbol: methods, callers, callees, imports, inheritance.

    Args:
        name: The symbol name to look up (e.g., "ProfileService", "create").
    """
    graph = _get_graph()
    if graph is None:
        return _no_index_error()
    result = _context(graph, name)
    return json.dumps(result, indent=2)


@mcp.tool()
def impact(target: str, direction: str = "upstream", max_depth: int = 3) -> str:
    """Analyze blast radius: what breaks if you change this symbol.

    Args:
        target: Symbol name to analyze.
        direction: "upstream" (what depends on this) or "downstream" (what this depends on).
        max_depth: How many hops to traverse (default 3).
    """
    graph = _get_graph()
    if graph is None:
        return _no_index_error()
    result = _impact(graph, target, direction=direction, max_depth=max_depth)
    return json.dumps(result, indent=2)


@mcp.tool()
def search(query_str: str, limit: int = 10) -> str:
    """Search symbols by name.

    Args:
        query_str: Search string to match against symbol names.
        limit: Maximum number of results (default 10).
    """
    graph = _get_graph()
    if graph is None:
        return _no_index_error()
    result = _query(graph, query_str, limit=limit)
    return json.dumps(result, indent=2)


@mcp.resource("pyxus://status")
def status() -> str:
    """Index freshness, symbol count, edge count, call resolution rate."""
    repo_path = os.environ.get("PYXUS_REPO_PATH") or _find_repo_root()
    metadata = get_index_metadata(repo_path)
    if metadata is None:
        return json.dumps({"error": "No Pyxus index found. Run `pyxus analyze` first."})
    return json.dumps(metadata, indent=2)
