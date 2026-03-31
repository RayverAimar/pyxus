"""Tests for web/serializers.py."""

from pyxus.graph.models import RelationKind, Relationship, Symbol, SymbolKind
from pyxus.graph.store import GraphStore
from pyxus.web.serializers import serialize_graph, serialize_module_graph


def _make_symbol(kind, file_path, name, line, **kwargs):
    """Create a Symbol with sensible defaults."""
    return Symbol(
        id=f"{kind.value}:{file_path}:{name}:{line}",
        name=name,
        kind=kind,
        file_path=file_path,
        start_line=line,
        end_line=line + 5,
        **kwargs,
    )


def _make_populated_graph():
    """Build a graph with modules, classes, functions, and various edges."""
    g = GraphStore()

    mod_a = _make_symbol(SymbolKind.MODULE, "a.py", "a.py", 0)
    mod_b = _make_symbol(SymbolKind.MODULE, "b.py", "b.py", 0)
    cls = _make_symbol(SymbolKind.CLASS, "a.py", "MyClass", 1)
    func = _make_symbol(SymbolKind.FUNCTION, "b.py", "helper", 1)
    method = _make_symbol(SymbolKind.METHOD, "a.py", "do_work", 5)

    for sym in [mod_a, mod_b, cls, func, method]:
        g.add_symbol(sym)

    g.add_relationship(Relationship(id="r1", source_id=mod_a.id, target_id=cls.id, kind=RelationKind.DEFINES))
    g.add_relationship(Relationship(id="r2", source_id=cls.id, target_id=method.id, kind=RelationKind.HAS_METHOD))
    g.add_relationship(
        Relationship(
            id="r3",
            source_id=method.id,
            target_id=func.id,
            kind=RelationKind.CALLS,
            confidence=0.9,
        )
    )
    g.add_relationship(Relationship(id="r4", source_id=mod_a.id, target_id=mod_b.id, kind=RelationKind.IMPORTS))

    return g


class TestSerializeGraph:
    def test_returns_nodes_and_edges(self):
        g = _make_populated_graph()
        result = serialize_graph(g)
        assert "nodes" in result
        assert "edges" in result
        assert "stats" in result
        assert len(result["nodes"]) == 5
        assert len(result["edges"]) == 4

    def test_node_fields(self):
        g = _make_populated_graph()
        result = serialize_graph(g)
        node = next(n for n in result["nodes"] if n["label"] == "MyClass")
        assert node["kind"] == "class"
        assert node["file"] == "a.py"
        assert node["line"] == 1
        assert node["size"] == 8  # CLASS size
        assert isinstance(node["degree"], int)
        assert isinstance(node["decorators"], list)
        assert isinstance(node["isExported"], bool)

    def test_edge_fields(self):
        g = _make_populated_graph()
        result = serialize_graph(g)
        calls_edge = next(e for e in result["edges"] if e["kind"] == "calls")
        assert "source" in calls_edge
        assert "target" in calls_edge
        assert calls_edge["confidence"] == 0.9

    def test_stats_include_counts(self):
        g = _make_populated_graph()
        result = serialize_graph(g)
        assert result["stats"]["nodeCount"] == 5
        assert result["stats"]["edgeCount"] == 4

    def test_metadata_forwarded_to_stats(self):
        g = _make_populated_graph()
        metadata = {
            "call_resolution_rate": 0.68,
            "indexed_at": "2026-03-15T10:00:00",
            "files_indexed": 10,
        }
        result = serialize_graph(g, metadata=metadata)
        assert result["stats"]["callResolutionRate"] == 0.68
        assert result["stats"]["indexedAt"] == "2026-03-15T10:00:00"
        assert result["stats"]["filesIndexed"] == 10

    def test_degree_counts_both_directions(self):
        g = _make_populated_graph()
        result = serialize_graph(g)
        # MyClass has: DEFINES incoming, HAS_METHOD outgoing = degree 2
        cls_node = next(n for n in result["nodes"] if n["label"] == "MyClass")
        assert cls_node["degree"] >= 2

    def test_node_sizes_by_kind(self):
        g = _make_populated_graph()
        result = serialize_graph(g)
        sizes = {n["label"]: n["size"] for n in result["nodes"]}
        assert sizes["a.py"] == 12  # MODULE
        assert sizes["MyClass"] == 8  # CLASS
        assert sizes["helper"] == 5  # FUNCTION
        assert sizes["do_work"] == 4  # METHOD


class TestSerializeModuleGraph:
    def test_only_module_nodes(self):
        g = _make_populated_graph()
        result = serialize_module_graph(g)
        kinds = {n["kind"] for n in result["nodes"]}
        assert kinds == {"module"}

    def test_only_import_edges(self):
        g = _make_populated_graph()
        result = serialize_module_graph(g)
        edge_kinds = {e["kind"] for e in result["edges"]}
        assert edge_kinds <= {"imports"}

    def test_counts_match(self):
        g = _make_populated_graph()
        result = serialize_module_graph(g)
        assert result["stats"]["nodeCount"] == len(result["nodes"])
        assert result["stats"]["edgeCount"] == len(result["edges"])

    def test_degree_reflects_import_edges(self):
        g = _make_populated_graph()
        result = serialize_module_graph(g)
        # mod_a imports mod_b → both should have degree 1
        for node in result["nodes"]:
            if node["label"] in ("a.py", "b.py"):
                assert node["degree"] == 1


class TestSerializeEdgeCases:
    def test_empty_graph(self):
        g = GraphStore()
        result = serialize_graph(g)
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["stats"]["nodeCount"] == 0

    def test_no_metadata(self):
        g = _make_populated_graph()
        result = serialize_graph(g)
        assert "callResolutionRate" not in result["stats"]

    def test_module_graph_empty(self):
        g = GraphStore()
        result = serialize_module_graph(g)
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_edge_metadata_included(self):
        g = GraphStore()
        mod = _make_symbol(SymbolKind.MODULE, "a.py", "a.py", 0)
        g.add_symbol(mod)
        func = _make_symbol(SymbolKind.FUNCTION, "a.py", "f", 1)
        g.add_symbol(func)
        g.add_relationship(
            Relationship(
                id="r1",
                source_id=mod.id,
                target_id=func.id,
                kind=RelationKind.DEFINES,
                metadata={"scope": "top_level"},
            )
        )
        result = serialize_graph(g)
        edge = result["edges"][0]
        assert edge["metadata"] == {"scope": "top_level"}
