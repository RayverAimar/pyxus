"""Tests for web/routes.py."""

import pytest
from starlette.testclient import TestClient

from pyxus.graph.models import RelationKind, Relationship, Symbol, SymbolKind
from pyxus.graph.store import GraphStore
from pyxus.web.app import create_app


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


@pytest.fixture
def app_with_graph():
    """A Starlette app with a populated graph for testing routes."""
    g = GraphStore()

    mod_a = _make_symbol(SymbolKind.MODULE, "a.py", "a.py", 0)
    mod_b = _make_symbol(SymbolKind.MODULE, "b.py", "b.py", 0)
    cls = _make_symbol(SymbolKind.CLASS, "a.py", "Service", 1)
    func = _make_symbol(SymbolKind.FUNCTION, "b.py", "helper", 1)
    method = _make_symbol(SymbolKind.METHOD, "a.py", "create", 5)

    for sym in [mod_a, mod_b, cls, func, method]:
        g.add_symbol(sym)

    g.add_relationship(Relationship(id="r1", source_id=mod_a.id, target_id=cls.id, kind=RelationKind.DEFINES))
    g.add_relationship(Relationship(id="r2", source_id=cls.id, target_id=method.id, kind=RelationKind.HAS_METHOD))
    g.add_relationship(Relationship(id="r3", source_id=method.id, target_id=func.id, kind=RelationKind.CALLS))
    g.add_relationship(Relationship(id="r4", source_id=mod_a.id, target_id=mod_b.id, kind=RelationKind.IMPORTS))

    metadata = {"indexed_at": "2026-03-15T10:00:00", "call_resolution_rate": 0.7, "files_indexed": 2}
    app = create_app(g, metadata=metadata, dev=True)
    return TestClient(app)


class TestGraphEndpoint:
    def test_returns_full_graph(self, app_with_graph):
        resp = app_with_graph.get("/api/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 5
        assert len(data["edges"]) == 4

    def test_module_level_filter(self, app_with_graph):
        resp = app_with_graph.get("/api/graph?level=module")
        assert resp.status_code == 200
        data = resp.json()
        kinds = {n["kind"] for n in data["nodes"]}
        assert kinds == {"module"}

    def test_stats_include_metadata(self, app_with_graph):
        resp = app_with_graph.get("/api/graph")
        data = resp.json()
        assert data["stats"]["callResolutionRate"] == 0.7


class TestContextEndpoint:
    def test_returns_symbol_context(self, app_with_graph):
        resp = app_with_graph.get("/api/context/Service")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"]["name"] == "Service"
        assert len(data["methods"]) == 1

    def test_not_found(self, app_with_graph):
        resp = app_with_graph.get("/api/context/Nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data


class TestImpactEndpoint:
    def test_upstream_impact(self, app_with_graph):
        resp = app_with_graph.get("/api/impact/helper")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target"]["name"] == "helper"
        assert data["direction"] == "upstream"

    def test_downstream_direction(self, app_with_graph):
        resp = app_with_graph.get("/api/impact/create?direction=downstream")
        assert resp.status_code == 200
        data = resp.json()
        assert data["direction"] == "downstream"


class TestSearchEndpoint:
    def test_search_by_name(self, app_with_graph):
        resp = app_with_graph.get("/api/search?q=Serv")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] >= 1
        assert any(r["name"] == "Service" for r in data["results"])

    def test_empty_query(self, app_with_graph):
        resp = app_with_graph.get("/api/search?q=")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] == 0

    def test_limit_parameter(self, app_with_graph):
        resp = app_with_graph.get("/api/search?q=e&limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) <= 1


class TestImportsEndpoint:
    def test_returns_module_dependencies(self, app_with_graph):
        resp = app_with_graph.get("/api/imports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_modules"] == 2
        assert data["total_dependencies"] == 1


class TestStatusEndpoint:
    def test_returns_metadata_and_counts(self, app_with_graph):
        resp = app_with_graph.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol_count"] == 5
        assert data["edge_count"] == 4
        assert data["indexed_at"] == "2026-03-15T10:00:00"
