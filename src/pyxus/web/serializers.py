"""Serializers for converting graph data to JSON-friendly dicts.

Transforms Symbol and Relationship objects from the knowledge graph into
flat dictionaries suitable for the frontend visualization layer. Provides
both full graph serialization and filtered views (module-only, class-only).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pyxus.graph.models import RelationKind, SymbolKind
from pyxus.graph.store import GraphStore

__all__ = ["serialize_graph", "serialize_module_graph"]


# ── Node size by symbol kind ────────────────────────────────────────────
_NODE_SIZES: dict[SymbolKind, int] = {
    SymbolKind.MODULE: 12,
    SymbolKind.CLASS: 8,
    SymbolKind.FUNCTION: 5,
    SymbolKind.METHOD: 4,
    SymbolKind.PROPERTY: 3,
    SymbolKind.CLASSMETHOD: 3,
    SymbolKind.STATICMETHOD: 3,
}

_DEFAULT_NODE_SIZE = 4


def serialize_graph(graph: GraphStore, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Serialize the full knowledge graph to a frontend-consumable dict.

    Returns nodes with visual attributes (size, kind) and edges with
    relationship metadata (kind, confidence). Stats are included for
    the status bar.
    """
    # Pre-compute degree for each symbol
    degree_map: dict[str, int] = defaultdict(int)
    for rel in graph.relationships():
        degree_map[rel.source_id] += 1
        degree_map[rel.target_id] += 1

    nodes = [
        {
            "id": symbol.id,
            "label": symbol.name,
            "kind": symbol.kind.value,
            "file": symbol.file_path,
            "line": symbol.start_line,
            "endLine": symbol.end_line,
            "decorators": list(symbol.decorators),
            "isExported": symbol.is_exported,
            "size": _NODE_SIZES.get(symbol.kind, _DEFAULT_NODE_SIZE),
            "degree": degree_map.get(symbol.id, 0),
        }
        for symbol in graph.symbols()
    ]

    edges = []
    for rel in graph.relationships():
        edge: dict[str, Any] = {
            "id": rel.id,
            "source": rel.source_id,
            "target": rel.target_id,
            "kind": rel.kind.value,
            "confidence": rel.confidence,
        }
        if rel.metadata:
            edge["metadata"] = rel.metadata
        edges.append(edge)

    stats: dict[str, Any] = {
        "nodeCount": graph.node_count,
        "edgeCount": graph.edge_count,
    }
    if metadata:
        if "call_resolution_rate" in metadata:
            stats["callResolutionRate"] = metadata["call_resolution_rate"]
        if "indexed_at" in metadata:
            stats["indexedAt"] = metadata["indexed_at"]
        if "files_indexed" in metadata:
            stats["filesIndexed"] = metadata["files_indexed"]

    return {"nodes": nodes, "edges": edges, "stats": stats}


def serialize_module_graph(graph: GraphStore) -> dict[str, Any]:
    """Serialize only MODULE nodes and IMPORTS edges for a high-level view.

    Provides a simplified dependency graph showing how modules connect
    to each other, without the noise of individual symbols.
    """
    nodes = []
    module_ids: set[str] = set()

    for symbol in graph.symbols():
        if symbol.kind != SymbolKind.MODULE:
            continue
        module_ids.add(symbol.id)
        nodes.append(
            {
                "id": symbol.id,
                "label": symbol.name,
                "kind": symbol.kind.value,
                "file": symbol.file_path,
                "line": symbol.start_line,
                "endLine": symbol.end_line,
                "decorators": [],
                "isExported": True,
                "size": _NODE_SIZES[SymbolKind.MODULE],
                "degree": 0,
            }
        )

    edges = []
    degree_map: dict[str, int] = defaultdict(int)

    for rel in graph.relationships():
        if rel.kind != RelationKind.IMPORTS:
            continue
        if rel.source_id not in module_ids or rel.target_id not in module_ids:
            continue
        degree_map[rel.source_id] += 1
        degree_map[rel.target_id] += 1
        edge: dict[str, Any] = {
            "id": rel.id,
            "source": rel.source_id,
            "target": rel.target_id,
            "kind": rel.kind.value,
            "confidence": rel.confidence,
        }
        if rel.metadata:
            edge["metadata"] = rel.metadata
        edges.append(edge)

    # Backfill degree now that we've counted edges
    for node in nodes:
        node["degree"] = degree_map.get(node["id"], 0)

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
        },
    }
