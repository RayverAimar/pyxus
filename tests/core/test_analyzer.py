"""Tests for core/analyzer.py — the pipeline orchestrator."""

from pyxus.core.analyzer import analyze
from pyxus.graph.models import RelationKind, SymbolKind
from tests.helpers import make_project


class TestFullPipeline:
    def test_analyzes_simple_project(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "models.py": ("class User:\n    def save(self):\n        pass\n"),
                "services.py": (
                    "from models import User\n"
                    "\n"
                    "class UserService:\n"
                    "    @staticmethod\n"
                    "    def create():\n"
                    "        user = User()\n"
                    "        user.save()\n"
                    "        return user\n"
                ),
            },
        )

        result = analyze(repo)

        assert result.stats.files_indexed == 2
        assert result.stats.files_skipped == 0
        assert result.stats.symbols_extracted > 0
        assert result.graph.node_count > 0
        assert result.graph.edge_count > 0

    def test_extracts_expected_symbols(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "app.py": ("class Service:\n    def process(self):\n        pass\n\ndef helper():\n    pass\n"),
            },
        )

        result = analyze(repo)
        symbols = result.graph.symbols()
        names = {s.name for s in symbols}

        assert "Service" in names
        assert "process" in names
        assert "helper" in names

    def test_creates_has_method_edges(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "models.py": (
                    "class User:\n"
                    "    def save(self):\n"
                    "        pass\n"
                    "    @property\n"
                    "    def name(self):\n"
                    "        return self._name\n"
                ),
            },
        )

        result = analyze(repo)
        user_sym = next(s for s in result.graph.symbols() if s.name == "User")
        methods = result.graph.successors_by_kind(user_sym.id, RelationKind.HAS_METHOD)
        method_names = {m.name for m in methods}

        assert "save" in method_names
        assert "name" in method_names

    def test_creates_extends_edges(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "models.py": ("class Base:\n    pass\n\nclass Child(Base):\n    pass\n"),
            },
        )

        result = analyze(repo)
        child = next(s for s in result.graph.symbols() if s.name == "Child")
        bases = result.graph.successors_by_kind(child.id, RelationKind.EXTENDS)
        assert any(b.name == "Base" for b in bases)

    def test_skips_syntax_errors(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "good.py": "def foo():\n    pass\n",
                "bad.py": "def broken(:\n",
            },
        )

        result = analyze(repo)
        assert result.stats.files_indexed == 1
        assert result.stats.files_skipped == 1

    def test_saves_graph_to_disk(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "app.py": "x = 1\n",
            },
        )

        analyze(repo)

        # Verify .pyxus/ was created with graph.pkl and metadata.json
        pyxus_dir = tmp_path / ".pyxus"
        assert pyxus_dir.exists()
        assert (pyxus_dir / "graph.pkl").exists()
        assert (pyxus_dir / "metadata.json").exists()

    def test_empty_project(self, tmp_path):
        result = analyze(str(tmp_path))
        assert result.stats.files_found == 0
        assert result.graph.node_count == 0

    def test_stats_include_call_resolution(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "main.py": ("class Foo:\n    def bar(self):\n        pass\n\nFoo.bar()\n"),
            },
        )

        result = analyze(repo)
        assert result.call_resolution is not None
        assert result.call_resolution.stats.total_calls >= 1
        assert result.stats.calls_resolved >= 1
        assert result.stats.call_resolution_rate > 0

    def test_extracts_expected_symbol_kinds(self, tmp_path):
        repo = make_project(
            tmp_path,
            {
                "app.py": ("class Service:\n    def process(self):\n        pass\n\ndef helper():\n    pass\n"),
            },
        )

        result = analyze(repo)
        symbols = {s.name: s for s in result.graph.symbols()}
        assert symbols["Service"].kind == SymbolKind.CLASS
        assert symbols["process"].kind == SymbolKind.METHOD
        assert symbols["helper"].kind == SymbolKind.FUNCTION


class TestIncrementalAnalysis:
    def test_incremental_without_existing_index(self, tmp_path):
        """Incremental with no prior index falls back to full analysis."""
        repo = make_project(tmp_path, {"app.py": "class Foo:\n    pass\n"})
        result = analyze(repo, incremental=True)
        assert result.stats.files_indexed >= 1
        assert result.graph.get_symbol_by_name("Foo")

    def test_incremental_with_existing_index(self, tmp_path):
        """Incremental with an existing index should succeed."""
        repo = make_project(tmp_path, {"app.py": "class Foo:\n    pass\n"})
        # First: full analysis
        analyze(repo)
        # Second: incremental (no changes)
        result = analyze(repo, incremental=True)
        assert result.graph.node_count >= 1
        assert result.graph.get_symbol_by_name("Foo")
