"""Persistence layer for the Pyxus knowledge graph.

Handles saving and loading the GraphStore to disk using pickle for fast
binary serialization. Also provides JSON export for human inspection and
a lightweight metadata file for quick status checks without loading the
full graph.

Storage layout inside the analyzed repository:
    .pyxus/
    ├── graph.pkl       # Full graph (pickle of GraphStore internals)
    └── metadata.json   # Summary stats: symbol count, timestamps, etc.

Security note on pickle:
    graph.pkl is written exclusively by save_graph() during ``pyxus analyze``.
    It lives inside the repo under .gitignore and is never transmitted over
    the network. We treat it as trusted local data. If the deployment model
    changes (e.g., shared/network-served repos), replace pickle with a safe
    format or add integrity verification (HMAC).
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pyxus import __version__
from pyxus.graph.store import GraphStore

__all__ = ["export_json", "get_index_metadata", "load_graph", "save_graph"]

logger = logging.getLogger("pyxus")

PYXUS_DIR = ".pyxus"
GRAPH_FILE = "graph.pkl"
METADATA_FILE = "metadata.json"


def _ensure_pyxus_dir(repo_path: str) -> Path:
    """Create the .pyxus/ directory if it doesn't exist and add it to .gitignore."""
    pyxus_dir = Path(repo_path) / PYXUS_DIR
    pyxus_dir.mkdir(exist_ok=True)

    gitignore_path = Path(repo_path) / ".gitignore"
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if ".pyxus/" not in content and ".pyxus" not in content:
            with gitignore_path.open("a") as f:
                f.write("\n# Pyxus analysis index\n.pyxus/\n")

    return pyxus_dir


def save_graph(store: GraphStore, repo_path: str, extra_metadata: dict[str, Any] | None = None) -> Path:
    """Save the graph to disk as a pickle file with accompanying metadata.

    Creates .pyxus/graph.pkl and .pyxus/metadata.json.
    """
    pyxus_dir = _ensure_pyxus_dir(repo_path)
    graph_path = pyxus_dir / GRAPH_FILE

    with graph_path.open("wb") as f:
        pickle.dump(store.to_state(), f, protocol=pickle.HIGHEST_PROTOCOL)

    metadata: dict[str, Any] = {
        "indexed_at": datetime.now(UTC).isoformat(),
        "pyxus_version": __version__,
        "symbol_count": store.node_count,
        "edge_count": store.edge_count,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    metadata_path = pyxus_dir / METADATA_FILE
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return graph_path


def load_graph(repo_path: str) -> GraphStore | None:
    """Load a previously saved graph from .pyxus/graph.pkl.

    Returns None if no saved graph exists.
    """
    graph_path = Path(repo_path) / PYXUS_DIR / GRAPH_FILE
    if not graph_path.exists():
        return None

    # See module docstring for security rationale on pickle usage
    try:
        with graph_path.open("rb") as f:
            state = pickle.load(f)  # noqa: S301
        return GraphStore.from_state(state)
    except (pickle.UnpicklingError, EOFError, AttributeError, KeyError) as e:
        logger.warning("Corrupted index at %s: %s. Run `pyxus analyze` to rebuild.", graph_path, e)
        return None


def get_index_metadata(repo_path: str) -> dict[str, Any] | None:
    """Read metadata.json without loading the full graph.

    Used by ``pyxus status`` to quickly show index information.
    """
    metadata_path = Path(repo_path) / PYXUS_DIR / METADATA_FILE
    if not metadata_path.exists():
        return None
    return json.loads(metadata_path.read_text())


def export_json(store: GraphStore, output_path: str) -> None:
    """Export the graph as human-readable JSON for inspection and debugging.

    Not intended for re-importing — use pickle for round-trip serialization.
    """
    symbols = [asdict(s) for s in store.symbols()]
    relationships = [asdict(r) for r in store.relationships()]

    data = {
        "exported_at": datetime.now(UTC).isoformat(),
        "symbol_count": len(symbols),
        "edge_count": len(relationships),
        "symbols": symbols,
        "relationships": relationships,
    }

    Path(output_path).write_text(json.dumps(data, indent=2, default=str))
