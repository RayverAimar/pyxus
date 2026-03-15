"""Query implementations for the Pyxus knowledge graph.

Provides the three main query functions exposed via the MCP server:

- ``context(name)``: 360-degree view of a symbol — its methods, callers,
  callees, importers, and inheritance chain.
- ``impact(target, direction, max_depth)``: blast radius analysis showing
  what breaks (upstream) or what is affected (downstream) if a symbol changes.
- ``query(search)``: substring search over symbol names with relevance ranking.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pyxus.graph.models import RelationKind, Relationship, RiskLevel, Symbol, SymbolKind
from pyxus.graph.store import GraphStore

__all__ = ["context", "impact", "query"]


# ── Risk assessment thresholds ────────────────────────────────────────────
# Based on the observation that symbols with many direct dependents
# have proportionally higher blast radius when modified.
_RISK_CRITICAL_THRESHOLD = 10
_RISK_HIGH_THRESHOLD = 5
_RISK_MEDIUM_THRESHOLD = 2

# ── Search relevance scoring ─────────────────────────────────────────────
_SCORE_EXACT = 1.0
_SCORE_EXACT_CASE_INSENSITIVE = 0.9
_SCORE_PREFIX = 0.8
_SCORE_CONTAINS = 0.5
_SCORE_EDGE_BOOST = 0.01  # Per incoming/outgoing edge
_SCORE_EDGE_BOOST_CAP = 0.1  # Maximum boost from connectivity


def context(graph: GraphStore, name: str) -> dict[str, Any]:
    """Get a 360-degree view of a symbol by name.

    If multiple symbols share the same name (e.g., ``create`` in different
    classes), returns a disambiguation list so the caller can choose.
    """
    matches = graph.get_symbol_by_name(name)
    if not matches:
        return {"error": f"No symbol found matching '{name}'"}

    matches = [m for m in matches if m.kind != SymbolKind.MODULE]
    if not matches:
        return {"error": f"No symbol found matching '{name}'"}

    if len(matches) > 1:
        return _disambiguation_response(matches)

    symbol = matches[0]

    methods = []
    if symbol.kind == SymbolKind.CLASS:
        method_symbols = graph.successors_by_kind(symbol.id, RelationKind.HAS_METHOD)
        methods = [
            {
                "name": m.name,
                "kind": m.kind.value,
                "decorators": list(m.decorators),
                "line": m.start_line,
            }
            for m in method_symbols
        ]

    incoming = _group_edges(graph.predecessors(symbol.id))
    outgoing = _group_edges(graph.successors(symbol.id))

    return {
        "symbol": {
            "name": symbol.name,
            "kind": symbol.kind.value,
            "file": symbol.file_path,
            "line": symbol.start_line,
            "end_line": symbol.end_line,
            "decorators": list(symbol.decorators),
            "exported": symbol.is_exported,
        },
        "methods": methods,
        "incoming": incoming,
        "outgoing": outgoing,
    }


def impact(
    graph: GraphStore,
    target: str,
    direction: str = "upstream",
    max_depth: int = 3,
) -> dict[str, Any]:
    """Analyze the blast radius of changing a symbol.

    Uses BFS to find all symbols reachable within ``max_depth`` hops,
    grouping results by distance. Upstream finds what depends on this
    symbol; downstream finds what this symbol depends on.
    """
    matches = graph.get_symbol_by_name(target)
    matches = [m for m in matches if m.kind != SymbolKind.MODULE]
    if not matches:
        return {"error": f"No symbol found matching '{target}'"}

    if len(matches) > 1:
        return _disambiguation_response(matches)

    symbol = matches[0]

    by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    visited: set[str] = {symbol.id}
    current_level = {symbol.id}

    for depth in range(1, max_depth + 1):
        next_level: set[str] = set()
        for sym_id in current_level:
            neighbors = graph.predecessors(sym_id) if direction == "upstream" else graph.successors(sym_id)

            for neighbor_sym, rel in neighbors:
                if neighbor_sym.id not in visited and neighbor_sym.kind != SymbolKind.MODULE:
                    visited.add(neighbor_sym.id)
                    next_level.add(neighbor_sym.id)
                    by_depth[depth].append(
                        {
                            "name": neighbor_sym.name,
                            "kind": neighbor_sym.kind.value,
                            "file": neighbor_sym.file_path,
                            "line": neighbor_sym.start_line,
                            "relationship": rel.kind.value,
                        }
                    )

        current_level = next_level
        if not current_level:
            break

    direct_count = len(by_depth.get(1, []))
    risk = _assess_risk(direct_count)
    total = sum(len(items) for items in by_depth.values())

    return {
        "target": {
            "name": symbol.name,
            "kind": symbol.kind.value,
            "file": symbol.file_path,
        },
        "direction": direction,
        "risk": risk,
        "summary": {
            "direct": direct_count,
            "indirect": total - direct_count,
            "total": total,
        },
        "by_depth": {str(d): items for d, items in sorted(by_depth.items())},
    }


def query(graph: GraphStore, search: str, limit: int = 10) -> dict[str, Any]:
    """Search symbols by name with relevance ranking.

    Ranking: exact > case-insensitive exact > prefix > contains.
    Connected symbols (more edges) get a small boost.
    """
    search_lower = search.lower()
    scored: list[tuple[float, dict[str, Any]]] = []

    for symbol in graph.symbols():
        if symbol.kind == SymbolKind.MODULE:
            continue

        name_lower = symbol.name.lower()

        if symbol.name == search:
            score = _SCORE_EXACT
        elif name_lower == search_lower:
            score = _SCORE_EXACT_CASE_INSENSITIVE
        elif name_lower.startswith(search_lower):
            score = _SCORE_PREFIX
        elif search_lower in name_lower:
            score = _SCORE_CONTAINS
        else:
            continue

        edge_count = len(graph.predecessors(symbol.id)) + len(graph.successors(symbol.id))
        score += min(edge_count * _SCORE_EDGE_BOOST, _SCORE_EDGE_BOOST_CAP)

        scored.append(
            (
                score,
                {
                    "name": symbol.name,
                    "kind": symbol.kind.value,
                    "file": symbol.file_path,
                    "line": symbol.start_line,
                    "score": round(score, 3),
                },
            )
        )

    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    results = [item for _, item in scored[:limit]]

    return {
        "query": search,
        "total_matches": len(scored),
        "results": results,
    }


# ── Private helpers ───────────────────────────────────────────────────────


def _disambiguation_response(matches: list[Symbol]) -> dict[str, Any]:
    """Build a disambiguation response when multiple symbols share a name."""
    return {
        "disambiguation": True,
        "candidates": [
            {
                "name": m.name,
                "kind": m.kind.value,
                "file": m.file_path,
                "line": m.start_line,
            }
            for m in matches
        ],
    }


def _group_edges(edges: list[tuple[Symbol, Relationship]]) -> dict[str, list[dict[str, Any]]]:
    """Group (symbol, relationship) pairs by relationship kind."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sym, rel in edges:
        if sym.kind == SymbolKind.MODULE:
            continue
        grouped[rel.kind.value].append(
            {
                "name": sym.name,
                "kind": sym.kind.value,
                "file": sym.file_path,
                "line": sym.start_line,
            }
        )
    return dict(grouped)


def _assess_risk(direct_dependents: int) -> RiskLevel:
    """Map direct dependent count to a risk level."""
    if direct_dependents > _RISK_CRITICAL_THRESHOLD:
        return RiskLevel.CRITICAL
    if direct_dependents > _RISK_HIGH_THRESHOLD:
        return RiskLevel.HIGH
    if direct_dependents > _RISK_MEDIUM_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
