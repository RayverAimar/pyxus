"""GraphStore: rustworkx PyDiGraph wrapper for the Pyxus knowledge graph.

Provides a high-level API over rustworkx's directed graph, speaking in terms
of Symbol and Relationship objects rather than raw node indices. Handles
index bookkeeping internally so callers never deal with integer indices.
"""

from __future__ import annotations

from collections import defaultdict

import rustworkx as rx

from pyxus.graph.models import RelationKind, Relationship, Symbol


class GraphStore:
    """Directed graph of Symbols (nodes) and Relationships (edges).

    Wraps a rustworkx.PyDiGraph with two responsibilities:
    1. Translate between symbol IDs (strings) and rustworkx node indices (ints).
    2. Provide typed traversal methods that return domain objects.

    Maintains secondary indexes (by name, by file) for fast lookups without
    full graph scans.

    Thread-safety: not thread-safe. Each MCP server process loads its own
    GraphStore instance — no shared mutable state between sessions.
    """

    def __init__(self) -> None:
        self._graph: rx.PyDiGraph = rx.PyDiGraph()
        self._id_to_index: dict[str, int] = {}
        self._name_to_ids: defaultdict[str, list[str]] = defaultdict(list)
        self._file_to_ids: defaultdict[str, list[str]] = defaultdict(list)

    # ── Mutations ─────────────────────────────────────────────────────────

    def add_symbol(self, symbol: Symbol) -> int:
        """Add a symbol node to the graph.

        Idempotent: if a symbol with the same ID already exists, returns the
        existing node index without creating a duplicate.
        """
        if symbol.id in self._id_to_index:
            return self._id_to_index[symbol.id]
        idx = self._graph.add_node(symbol)
        self._id_to_index[symbol.id] = idx
        self._name_to_ids[symbol.name].append(symbol.id)
        self._file_to_ids[symbol.file_path].append(symbol.id)
        return idx

    def add_relationship(self, rel: Relationship) -> int:
        """Add a directed edge between two existing symbols.

        Raises:
            KeyError: If either the source or target symbol ID is not in the graph.
        """
        src_idx = self._id_to_index.get(rel.source_id)
        tgt_idx = self._id_to_index.get(rel.target_id)
        if src_idx is None:
            raise KeyError(f"Source symbol not found: {rel.source_id}")
        if tgt_idx is None:
            raise KeyError(f"Target symbol not found: {rel.target_id}")
        return self._graph.add_edge(src_idx, tgt_idx, rel)

    # ── Lookups ───────────────────────────────────────────────────────────

    def get_symbol(self, symbol_id: str) -> Symbol | None:
        """Look up a symbol by its unique ID. Returns None if not found."""
        idx = self._id_to_index.get(symbol_id)
        if idx is None:
            return None
        return self._graph[idx]

    def get_symbol_by_name(self, name: str) -> list[Symbol]:
        """Find all symbols matching a given name.

        O(k) where k is the number of symbols with that name (typically 1-3),
        not O(n) over the entire graph.
        """
        return [self._graph[self._id_to_index[sid]] for sid in self._name_to_ids.get(name, [])]

    def get_symbols_in_file(self, file_path: str) -> list[Symbol]:
        """Get every symbol defined in a specific source file."""
        return [self._graph[self._id_to_index[sid]] for sid in self._file_to_ids.get(file_path, [])]

    # ── Graph traversal ───────────────────────────────────────────────────

    def predecessors(self, symbol_id: str) -> list[tuple[Symbol, Relationship]]:
        """Get all (symbol, relationship) pairs that point TO this symbol.

        For a function, predecessors include its callers. For a class,
        predecessors include files that import it or classes that extend it.
        """
        idx = self._id_to_index.get(symbol_id)
        if idx is None:
            return []
        result = []
        for pred_idx in self._graph.predecessor_indices(idx):
            for rel in self._graph.get_all_edge_data(pred_idx, idx):
                result.append((self._graph[pred_idx], rel))
        return result

    def successors(self, symbol_id: str) -> list[tuple[Symbol, Relationship]]:
        """Get all (symbol, relationship) pairs this symbol points TO.

        For a function, successors include its callees. For a class,
        successors include its methods and base classes.
        """
        idx = self._id_to_index.get(symbol_id)
        if idx is None:
            return []
        result = []
        for succ_idx in self._graph.successor_indices(idx):
            for rel in self._graph.get_all_edge_data(idx, succ_idx):
                result.append((self._graph[succ_idx], rel))
        return result

    def predecessors_by_kind(self, symbol_id: str, kind: RelationKind) -> list[Symbol]:
        """Get predecessor symbols filtered to a specific relationship kind."""
        return [sym for sym, rel in self.predecessors(symbol_id) if rel.kind == kind]

    def successors_by_kind(self, symbol_id: str, kind: RelationKind) -> list[Symbol]:
        """Get successor symbols filtered to a specific relationship kind."""
        return [sym for sym, rel in self.successors(symbol_id) if rel.kind == kind]

    # ── Bulk removal (for incremental re-indexing) ────────────────────────

    def remove_symbols_in_file(self, file_path: str) -> int:
        """Remove all symbols from a given file, along with their edges.

        Used during incremental re-analysis: when a file changes, its old
        symbols are removed before re-extracting from the updated source.

        Returns the number of symbols removed.
        """
        ids_to_remove = list(self._file_to_ids.get(file_path, []))
        for sid in ids_to_remove:
            idx = self._id_to_index.pop(sid)
            symbol = self._graph[idx]
            self._name_to_ids[symbol.name].remove(sid)
            # Clean up empty name entries to avoid memory leak over many incremental cycles
            if not self._name_to_ids[symbol.name]:
                del self._name_to_ids[symbol.name]
            self._graph.remove_node(idx)
        if file_path in self._file_to_ids:
            del self._file_to_ids[file_path]
        return len(ids_to_remove)

    # ── Serialization ────────────────────────────────────────────────────

    def to_state(self) -> dict:
        """Export internal state for serialization.

        Returns a dict that can be passed to ``from_state()`` to reconstruct
        the GraphStore. This is the stable serialization contract — external
        code should use this instead of accessing private attributes.
        """
        return {
            "graph": self._graph,
            "id_to_index": self._id_to_index,
        }

    @classmethod
    def from_state(cls, state: dict) -> GraphStore:
        """Reconstruct a GraphStore from a previously exported state dict.

        Rebuilds secondary indexes (by name, by file) that are not persisted.
        """
        store = cls()
        store._graph = state["graph"]
        store._id_to_index = state["id_to_index"]
        # Rebuild secondary indexes from the deserialized data
        for sid, idx in store._id_to_index.items():
            symbol = store._graph[idx]
            store._name_to_ids[symbol.name].append(sid)
            store._file_to_ids[symbol.file_path].append(sid)
        return store

    # ── Stats ─────────────────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        """Total number of symbol nodes in the graph."""
        return self._graph.num_nodes()

    @property
    def edge_count(self) -> int:
        """Total number of relationship edges in the graph."""
        return self._graph.num_edges()

    def symbols(self) -> list[Symbol]:
        """Return a list of all symbols currently in the graph."""
        return [self._graph[idx] for idx in self._id_to_index.values()]

    def relationships(self) -> list[Relationship]:
        """Return a list of all relationships currently in the graph."""
        return list(self._graph.edges())
