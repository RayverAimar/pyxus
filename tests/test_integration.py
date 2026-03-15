"""Integration tests: run the full pipeline on fixture projects.

These tests verify that the entire analysis pipeline works end-to-end
on realistic (but small) Python codebases. They test the interaction
between all components rather than testing components in isolation.
"""

from pathlib import Path

import pytest

from pyxus.core.analyzer import analyze
from pyxus.graph.models import RelationKind, SymbolKind
from pyxus.graph.persistence import load_graph
from pyxus.graph.queries import context, impact, query

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSimpleProject:
    """Integration tests on the simple_project fixture."""

    @pytest.fixture(autouse=True)
    def _analyze(self, tmp_path):
        """Copy fixture to tmp and run analysis."""
        import shutil

        project_dir = tmp_path / "simple_project"
        shutil.copytree(FIXTURES_DIR / "simple_project", project_dir)
        self.result = analyze(str(project_dir))
        self.graph = self.result.graph

    def test_files_indexed(self):
        assert self.result.stats.files_indexed >= 5

    def test_no_files_skipped(self):
        assert self.result.stats.files_skipped == 0

    def test_symbols_extracted(self):
        """All expected classes and functions are found."""
        names = {s.name for s in self.graph.symbols() if s.kind != SymbolKind.MODULE}
        assert "Base" in names
        assert "User" in names
        assert "UserService" in names
        assert "validate_name" in names
        assert "compute" in names

    def test_inheritance_detected(self):
        """User extends Base."""
        user = next(s for s in self.graph.symbols() if s.name == "User")
        bases = self.graph.successors_by_kind(user.id, RelationKind.EXTENDS)
        assert any(b.name == "Base" for b in bases)

    def test_methods_attached_to_classes(self):
        """User class has save, delete (inherited from Base), and its own methods."""
        user = next(s for s in self.graph.symbols() if s.name == "User")
        methods = self.graph.successors_by_kind(user.id, RelationKind.HAS_METHOD)
        method_names = {m.name for m in methods}
        assert "display_name" in method_names
        assert "create" in method_names
        assert "from_dict" in method_names
        assert "__init__" in method_names

    def test_method_kinds_correct(self):
        """@property, @staticmethod, @classmethod classified correctly."""
        symbols = {s.name: s for s in self.graph.symbols()}
        assert symbols["display_name"].kind == SymbolKind.PROPERTY
        assert symbols["create"].kind == SymbolKind.STATICMETHOD
        assert symbols["from_dict"].kind == SymbolKind.CLASSMETHOD

    def test_context_query_works(self):
        result = context(self.graph, "User")
        assert result["symbol"]["name"] == "User"
        assert result["symbol"]["kind"] == "class"
        assert len(result["methods"]) >= 4

    def test_impact_query_works(self):
        result = impact(self.graph, "User", direction="upstream")
        assert result["target"]["name"] == "User"
        assert "risk" in result

    def test_search_query_works(self):
        result = query(self.graph, "user")
        assert result["total_matches"] >= 1
        names = {r["name"] for r in result["results"]}
        assert "User" in names or "UserService" in names


class TestComplexProject:
    """Integration tests on the complex_project fixture."""

    @pytest.fixture(autouse=True)
    def _analyze(self, tmp_path):
        import shutil

        project_dir = tmp_path / "complex_project"
        shutil.copytree(FIXTURES_DIR / "complex_project", project_dir)
        self.result = analyze(str(project_dir))
        self.graph = self.result.graph

    def test_files_indexed(self):
        assert self.result.stats.files_indexed >= 4

    def test_deep_inheritance_chain(self):
        """JSONProcessor → TransformProcessor → BaseProcessor."""
        names = {s.name: s for s in self.graph.symbols() if s.kind == SymbolKind.CLASS}
        assert "BaseProcessor" in names
        assert "TransformProcessor" in names
        assert "JSONProcessor" in names

        # TransformProcessor extends BaseProcessor
        tp = names["TransformProcessor"]
        tp_bases = self.graph.successors_by_kind(tp.id, RelationKind.EXTENDS)
        assert any(b.name == "BaseProcessor" for b in tp_bases)

        # JSONProcessor extends TransformProcessor
        jp = names["JSONProcessor"]
        jp_bases = self.graph.successors_by_kind(jp.id, RelationKind.EXTENDS)
        assert any(b.name == "TransformProcessor" for b in jp_bases)

    def test_cross_module_class_detected(self):
        """CustomProcessor defined in api/handlers.py extends core/base.py's BaseProcessor."""
        cp = next(s for s in self.graph.symbols() if s.name == "CustomProcessor")
        bases = self.graph.successors_by_kind(cp.id, RelationKind.EXTENDS)
        assert any(b.name == "BaseProcessor" for b in bases)

    def test_async_function_extracted(self):
        """async_handler should be extracted as a FUNCTION."""
        async_funcs = [s for s in self.graph.symbols() if s.name == "async_handler"]
        assert len(async_funcs) == 1
        assert async_funcs[0].kind == SymbolKind.FUNCTION

    def test_abstract_method_extracted(self):
        """BaseProcessor.process should be a METHOD."""
        process_methods = [s for s in self.graph.symbols() if s.name == "process" and s.kind == SymbolKind.METHOD]
        assert len(process_methods) >= 1

    def test_impact_on_base_class(self):
        """Changing BaseProcessor should have high impact (many dependents)."""
        result = impact(self.graph, "BaseProcessor", direction="upstream")
        assert result["summary"]["total"] >= 1

    def test_context_shows_registry_methods(self):
        result = context(self.graph, "Registry")
        assert result["symbol"]["kind"] == "class"
        method_names = {m["name"] for m in result["methods"]}
        assert "register" in method_names
        assert "get" in method_names
        assert "process" in method_names


class TestGraphPersistence:
    """Test that the graph can be saved and reloaded correctly."""

    def test_save_and_reload(self, tmp_path):
        import shutil

        project_dir = tmp_path / "project"
        shutil.copytree(FIXTURES_DIR / "simple_project", project_dir)

        # Analyze and save
        result1 = analyze(str(project_dir))

        # Reload from disk
        loaded = load_graph(str(project_dir))
        assert loaded is not None
        assert loaded.node_count == result1.graph.node_count
        assert loaded.edge_count == result1.graph.edge_count

        # Queries still work on loaded graph
        ctx = context(loaded, "User")
        assert ctx["symbol"]["name"] == "User"
