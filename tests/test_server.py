"""Tests for server.py — MCP server tool functions."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the tool functions directly (they call _get_graph internally)
import pyxus.server as server_mod
from pyxus.graph.models import RelationKind, Relationship, Symbol, SymbolKind
from pyxus.graph.persistence import save_graph
from pyxus.graph.store import GraphStore


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the server's graph cache between tests."""
    server_mod._graph_cache = None
    server_mod._repo_path = None
    yield
    server_mod._graph_cache = None
    server_mod._repo_path = None


def _make_indexed_project(tmp_path: Path) -> GraphStore:
    """Create a minimal indexed project with a saved graph for testing."""
    store = GraphStore()
    cls = Symbol(
        id="class:app.py:Foo:1",
        name="Foo",
        kind=SymbolKind.CLASS,
        file_path="app.py",
        start_line=1,
        end_line=10,
    )
    method = Symbol(
        id="method:app.py:bar:3",
        name="bar",
        kind=SymbolKind.METHOD,
        file_path="app.py",
        start_line=3,
        end_line=8,
    )
    store.add_symbol(cls)
    store.add_symbol(method)
    store.add_relationship(
        Relationship(
            id="r1",
            source_id=cls.id,
            target_id=method.id,
            kind=RelationKind.HAS_METHOD,
        )
    )
    save_graph(store, str(tmp_path))
    return store


class TestContextTool:
    def test_returns_symbol_info(self, tmp_path):
        _make_indexed_project(tmp_path)
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.context("Foo"))
        assert result["symbol"]["name"] == "Foo"
        assert result["symbol"]["kind"] == "class"

    def test_no_index_returns_error(self, tmp_path):
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.context("Foo"))
        assert "error" in result
        assert "pyxus analyze" in result["error"]


class TestImpactTool:
    def test_returns_impact(self, tmp_path):
        _make_indexed_project(tmp_path)
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.impact("Foo"))
        assert result["target"]["name"] == "Foo"
        assert "risk" in result

    def test_no_index_returns_error(self, tmp_path):
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.impact("Foo"))
        assert "error" in result


class TestSearchTool:
    def test_returns_results(self, tmp_path):
        _make_indexed_project(tmp_path)
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.search("Foo"))
        assert result["total_matches"] >= 1

    def test_no_index_returns_error(self, tmp_path):
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.search("Foo"))
        assert "error" in result


class TestStatusResource:
    def test_returns_metadata(self, tmp_path):
        _make_indexed_project(tmp_path)
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.status())
        assert "symbol_count" in result
        assert result["symbol_count"] == 2

    def test_no_index_returns_error(self, tmp_path):
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result = json.loads(server_mod.status())
        assert "error" in result


class TestGraphCaching:
    def test_graph_cached_on_second_call(self, tmp_path):
        """Second tool call should use the cached graph, not reload from disk."""
        _make_indexed_project(tmp_path)
        with patch.dict("os.environ", {"PYXUS_REPO_PATH": str(tmp_path)}):
            result1 = json.loads(server_mod.context("Foo"))
            # Graph is now cached
            assert server_mod._graph_cache is not None
            result2 = json.loads(server_mod.context("Foo"))
        assert result1 == result2
