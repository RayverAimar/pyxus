"""Tests for core/import_resolver.py."""

from pyxus.core.file_walker import SourceFile
from pyxus.core.import_resolver import (
    build_file_index,
    resolve_imports,
)
from pyxus.graph.models import ImportScope, RelationKind


def _make_source_file(path: str, content: str = "") -> SourceFile:
    """Create a SourceFile for testing."""
    return SourceFile(path=path, absolute_path=f"/repo/{path}", content=content)


def _make_file_index(*paths: str) -> tuple[dict[str, str], dict[str, SourceFile]]:
    """Create a file index and all_files dict from a list of file paths."""
    files = [_make_source_file(p) for p in paths]
    index = build_file_index(files)
    all_files = {f.path: f for f in files}
    return index, all_files


class TestBuildFileIndex:
    def test_simple_module(self):
        files = [_make_source_file("utils.py")]
        index = build_file_index(files)
        assert index["utils"] == "utils.py"

    def test_nested_module(self):
        files = [_make_source_file("services/profiles.py")]
        index = build_file_index(files)
        assert index["services.profiles"] == "services/profiles.py"

    def test_package_init(self):
        files = [_make_source_file("models/__init__.py")]
        index = build_file_index(files)
        assert index["models"] == "models/__init__.py"

    def test_deep_package(self):
        files = [_make_source_file("api/viewsets/__init__.py"), _make_source_file("api/viewsets/profiles.py")]
        index = build_file_index(files)
        assert index["api.viewsets"] == "api/viewsets/__init__.py"
        assert index["api.viewsets.profiles"] == "api/viewsets/profiles.py"


class TestAbsoluteImports:
    def test_import_module(self):
        index, all_files = _make_file_index("main.py", "utils.py")
        source = _make_source_file("main.py", "import utils\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert result.resolved[0].target_file == "utils.py"

    def test_from_import(self):
        index, all_files = _make_file_index("main.py", "services/profiles.py")
        source = _make_source_file("main.py", "from services.profiles import ProfileService\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert result.resolved[0].target_file == "services/profiles.py"
        assert result.resolved[0].imported_names == ["ProfileService"]

    def test_from_package_import_module(self):
        """from services import profiles → resolves to services/profiles.py."""
        index, all_files = _make_file_index(
            "main.py",
            "services/__init__.py",
            "services/profiles.py",
        )
        source = _make_source_file("main.py", "from services import profiles\n")
        result = resolve_imports(source, index, all_files)
        # Should resolve: either services/__init__.py or services/profiles.py
        targets = {r.target_file for r in result.resolved}
        assert "services/profiles.py" in targets or "services/__init__.py" in targets

    def test_external_package_ignored(self):
        """Imports of packages not in the repo (e.g., django) produce no resolved imports."""
        index, all_files = _make_file_index("main.py")
        source = _make_source_file("main.py", "import django\nfrom django.db import models\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 0
        # External packages are not counted as unresolved — only internal failures are
        assert len(result.unresolved) == 0


class TestRelativeImports:
    def test_dot_import(self):
        """from . import models → resolves within same package."""
        index, all_files = _make_file_index(
            "pkg/__init__.py",
            "pkg/main.py",
            "pkg/models.py",
        )
        source = _make_source_file("pkg/main.py", "from . import models\n")
        result = resolve_imports(source, index, all_files)
        targets = {r.target_file for r in result.resolved}
        assert "pkg/models.py" in targets or "pkg/__init__.py" in targets

    def test_dotdot_import(self):
        """from .. import utils → resolves to parent package."""
        index, all_files = _make_file_index(
            "pkg/__init__.py",
            "pkg/sub/__init__.py",
            "pkg/sub/deep.py",
            "pkg/utils.py",
        )
        source = _make_source_file("pkg/sub/deep.py", "from .. import utils\n")
        result = resolve_imports(source, index, all_files)
        targets = {r.target_file for r in result.resolved}
        assert "pkg/utils.py" in targets or "pkg/__init__.py" in targets

    def test_relative_from_module(self):
        """from .models import User → resolves within same package."""
        index, all_files = _make_file_index(
            "app/__init__.py",
            "app/views.py",
            "app/models.py",
        )
        source = _make_source_file("app/views.py", "from .models import User\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert result.resolved[0].target_file == "app/models.py"
        assert result.resolved[0].is_relative is True


class TestRelationships:
    def test_creates_imports_edge(self):
        index, all_files = _make_file_index("main.py", "utils.py")
        source = _make_source_file("main.py", "import utils\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.relationships) == 1
        rel = result.relationships[0]
        assert rel.kind == RelationKind.IMPORTS
        assert "main.py" in rel.source_id
        assert "utils.py" in rel.target_id

    def test_no_duplicate_edges(self):
        """Multiple imports from the same file should produce only one IMPORTS edge."""
        index, all_files = _make_file_index("main.py", "utils.py")
        source = _make_source_file("main.py", "from utils import foo\nfrom utils import bar\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.relationships) == 1


class TestEdgeCases:
    def test_syntax_error_returns_empty(self):
        index, all_files = _make_file_index("main.py")
        source = _make_source_file("main.py", "from import\n")
        result = resolve_imports(source, index, all_files)
        assert result.resolved == []

    def test_star_import(self):
        """from module import * should resolve to the module file."""
        index, all_files = _make_file_index("main.py", "types.py")
        source = _make_source_file("main.py", "from types import *\n")
        # "types" collides with stdlib, but our index only has repo files
        # This tests the mechanism, not stdlib resolution
        index["types"] = "types.py"
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1

    def test_relative_import_too_many_dots(self):
        """from .... import x — more dots than directory depth should not crash."""
        index, all_files = _make_file_index("pkg/mod.py")
        source = _make_source_file("pkg/mod.py", "from .... import something\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 0

    def test_multiple_names_from_one_module(self):
        """from module import a, b, c."""
        index, all_files = _make_file_index("main.py", "utils.py")
        source = _make_source_file("main.py", "from utils import foo, bar, baz\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert set(result.resolved[0].imported_names) == {"foo", "bar", "baz"}

    def test_import_from_submodule(self):
        """from pkg.sub import func — where pkg.sub is a module file."""
        index, all_files = _make_file_index("main.py", "pkg/__init__.py", "pkg/sub.py")
        source = _make_source_file("main.py", "from pkg.sub import func\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert result.resolved[0].target_file == "pkg/sub.py"


class TestSrcLayout:
    """Tests for src/ layout projects where file paths start with src/."""

    def test_file_index_registers_without_src_prefix(self):
        """src/pkg/module.py should be indexed as both src.pkg.module and pkg.module."""
        files = [_make_source_file("src/mylib/core/engine.py")]
        index = build_file_index(files)
        assert index["src.mylib.core.engine"] == "src/mylib/core/engine.py"
        assert index["mylib.core.engine"] == "src/mylib/core/engine.py"

    def test_file_index_src_package_init(self):
        """src/pkg/__init__.py should be indexed as both src.pkg and pkg."""
        files = [_make_source_file("src/mylib/__init__.py")]
        index = build_file_index(files)
        assert index["src.mylib"] == "src/mylib/__init__.py"
        assert index["mylib"] == "src/mylib/__init__.py"

    def test_file_index_src_deep_package(self):
        """src/pkg/sub/__init__.py should be indexed without src prefix."""
        files = [_make_source_file("src/mylib/core/__init__.py")]
        index = build_file_index(files)
        assert index["mylib.core"] == "src/mylib/core/__init__.py"

    def test_absolute_import_resolves_in_src_layout(self):
        """Absolute imports should resolve when files live under src/."""
        index, all_files = _make_file_index(
            "src/mylib/__init__.py",
            "src/mylib/core/__init__.py",
            "src/mylib/core/engine.py",
            "src/mylib/cli.py",
        )
        source = _make_source_file(
            "src/mylib/cli.py",
            "from mylib.core.engine import run\n",
        )
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert result.resolved[0].target_file == "src/mylib/core/engine.py"

    def test_import_creates_edge_in_src_layout(self):
        """IMPORTS edge should be created for src-layout absolute imports."""
        index, all_files = _make_file_index(
            "src/myapp/__init__.py",
            "src/myapp/models.py",
            "src/myapp/views.py",
        )
        source = _make_source_file(
            "src/myapp/views.py",
            "from myapp.models import User\n",
        )
        result = resolve_imports(source, index, all_files)
        assert len(result.relationships) == 1
        rel = result.relationships[0]
        assert rel.kind == RelationKind.IMPORTS
        assert "views.py" in rel.source_id
        assert "models.py" in rel.target_id

    def test_multiple_src_imports_resolve(self):
        """Multiple absolute imports should each resolve in src/ layout."""
        index, all_files = _make_file_index(
            "src/pkg/__init__.py",
            "src/pkg/core/__init__.py",
            "src/pkg/core/store.py",
            "src/pkg/core/models.py",
            "src/pkg/server.py",
        )
        source = _make_source_file(
            "src/pkg/server.py",
            "from pkg.core.store import GraphStore\nfrom pkg.core.models import Symbol\n",
        )
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 2
        targets = {r.target_file for r in result.resolved}
        assert targets == {"src/pkg/core/store.py", "src/pkg/core/models.py"}

    def test_non_src_files_unaffected(self):
        """Files not under src/ should not gain spurious index entries."""
        files = [_make_source_file("tests/test_foo.py")]
        index = build_file_index(files)
        assert "tests.test_foo" in index
        assert "test_foo" not in index  # should NOT strip "tests."


class TestImportLocations:
    def test_top_level_import(self):
        """Top-level imports are tagged as scope=top_level."""
        index, all_files = _make_file_index("main.py", "utils.py")
        source = _make_source_file("main.py", "from utils import helper\n")
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert result.resolved[0].location is not None
        assert result.resolved[0].location.scope == ImportScope.TOP_LEVEL
        assert result.resolved[0].location.function is None

    def test_local_import_in_function(self):
        """Imports inside a function are tagged as scope=local with function name."""
        index, all_files = _make_file_index("main.py", "utils.py")
        code = "def process():\n    from utils import helper\n    helper()\n"
        source = _make_source_file("main.py", code)
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 1
        assert result.resolved[0].location is not None
        assert result.resolved[0].location.scope == ImportScope.LOCAL
        assert result.resolved[0].location.function == "process"

    def test_same_target_top_and_local(self):
        """Same module imported top-level AND locally → one edge, both locations in metadata."""
        index, all_files = _make_file_index("main.py", "utils.py")
        code = "from utils import foo\n\ndef process():\n    from utils import bar\n"
        source = _make_source_file("main.py", code)
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 2
        # One relationship edge with both locations
        assert len(result.relationships) == 1
        meta = result.relationships[0].metadata
        assert meta["has_top_level"] is True
        assert meta["has_local"] is True
        assert len(meta["locations"]) == 2

    def test_multiple_local_imports_different_functions(self):
        """Same module imported in two different functions → one edge, two local locations."""
        index, all_files = _make_file_index("main.py", "utils.py")
        code = "def foo():\n    from utils import a\n\ndef bar():\n    from utils import b\n"
        source = _make_source_file("main.py", code)
        result = resolve_imports(source, index, all_files)
        assert len(result.resolved) == 2
        assert len(result.relationships) == 1
        meta = result.relationships[0].metadata
        assert meta["has_local"] is True
        assert meta["has_top_level"] is False
        locations = meta["locations"]
        functions = {loc["function"] for loc in locations}
        assert functions == {"foo", "bar"}
