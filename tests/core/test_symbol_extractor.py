"""Tests for core/symbol_extractor.py."""

from pyxus.core.file_walker import SourceFile
from pyxus.core.symbol_extractor import extract_symbols
from pyxus.graph.models import RelationKind, SymbolKind


def _make_extraction(code: str, path: str = "test.py"):
    """Extract symbols from a code string for testing."""
    sf = SourceFile(path=path, absolute_path=f"/tmp/{path}", content=code)
    return extract_symbols(sf)


class TestClassExtraction:
    def test_extracts_class(self):
        result = _make_extraction("class Foo:\n    pass\n")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert cls.name == "Foo"
        assert cls.file_path == "test.py"
        assert cls.start_line == 1
        assert cls.end_line == 2
        assert cls.is_exported is True
        assert cls.decorators == ()

    def test_class_with_decorator(self):
        result = _make_extraction("@dataclass\nclass Foo:\n    pass\n")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert cls.name == "Foo"
        assert "dataclass" in cls.decorators
        assert cls.start_line == 2

    def test_private_class_not_exported(self):
        result = _make_extraction("class _Internal:\n    pass\n")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert cls.name == "_Internal"
        assert cls.is_exported is False


class TestMethodExtraction:
    def test_method_inside_class(self):
        code = "class Foo:\n    def bar(self):\n        pass\n"
        result = _make_extraction(code)
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) == 1
        assert methods[0].name == "bar"
        assert methods[0].file_path == "test.py"
        assert methods[0].start_line == 2

    def test_staticmethod(self):
        code = "class Foo:\n    @staticmethod\n    def create():\n        pass\n"
        result = _make_extraction(code)
        statics = [s for s in result.symbols if s.kind == SymbolKind.STATICMETHOD]
        assert len(statics) == 1
        assert statics[0].name == "create"
        assert "staticmethod" in statics[0].decorators
        assert statics[0].is_exported is True

    def test_classmethod(self):
        code = "class Foo:\n    @classmethod\n    def from_dict(cls):\n        pass\n"
        result = _make_extraction(code)
        classmethods = [s for s in result.symbols if s.kind == SymbolKind.CLASSMETHOD]
        assert len(classmethods) == 1
        assert classmethods[0].name == "from_dict"
        assert "classmethod" in classmethods[0].decorators

    def test_property(self):
        code = "class Foo:\n    @property\n    def name(self):\n        return self._name\n"
        result = _make_extraction(code)
        props = [s for s in result.symbols if s.kind == SymbolKind.PROPERTY]
        assert len(props) == 1
        assert props[0].name == "name"
        assert "property" in props[0].decorators


class TestFunctionExtraction:
    def test_top_level_function(self):
        code = "def helper():\n    pass\n"
        result = _make_extraction(code)
        funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "helper"
        assert funcs[0].start_line == 1
        assert funcs[0].is_exported is True

    def test_async_function(self):
        code = "async def fetch():\n    pass\n"
        result = _make_extraction(code)
        funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "fetch"
        assert funcs[0].start_line == 1

    def test_async_method(self):
        code = "class Api:\n    async def get(self):\n        pass\n"
        result = _make_extraction(code)
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) == 1
        assert methods[0].name == "get"
        assert methods[0].start_line == 2


class TestNestedClass:
    def test_nested_class_extracted(self):
        code = "class Outer:\n    class Inner:\n        pass\n"
        result = _make_extraction(code)
        classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
        assert len(classes) == 2
        assert {c.name for c in classes} == {"Outer", "Inner"}

    def test_nested_class_has_method_edge(self):
        code = "class Outer:\n    class Meta:\n        pass\n"
        result = _make_extraction(code)
        has_method_edges = [r for r in result.relationships if r.kind == RelationKind.HAS_METHOD]
        edge = next(r for r in has_method_edges if "Meta" in r.target_id)
        assert "Outer" in edge.source_id


class TestRelationships:
    def test_defines_edge_for_top_level_class(self):
        result = _make_extraction("class Foo:\n    pass\n")
        defines = [r for r in result.relationships if r.kind == RelationKind.DEFINES]
        assert len(defines) == 1
        assert "module" in defines[0].source_id
        assert "Foo" in defines[0].target_id

    def test_defines_edge_for_top_level_function(self):
        result = _make_extraction("def helper():\n    pass\n")
        defines = [r for r in result.relationships if r.kind == RelationKind.DEFINES]
        assert len(defines) == 1
        assert "module" in defines[0].source_id
        assert "helper" in defines[0].target_id

    def test_has_method_edge_for_class_method(self):
        code = "class Foo:\n    def bar(self):\n        pass\n"
        result = _make_extraction(code)
        has_method = [r for r in result.relationships if r.kind == RelationKind.HAS_METHOD]
        assert len(has_method) == 1
        assert "Foo" in has_method[0].source_id
        assert "bar" in has_method[0].target_id

    def test_module_symbol_created(self):
        result = _make_extraction("x = 1\n")
        modules = [s for s in result.symbols if s.kind == SymbolKind.MODULE]
        assert len(modules) == 1
        assert modules[0].file_path == "test.py"


class TestEdgeCases:
    def test_syntax_error_returns_empty(self):
        sf = SourceFile(path="bad.py", absolute_path="/tmp/bad.py", content="def broken(:\n")
        result = extract_symbols(sf)
        assert result.symbols == []
        assert result.relationships == []

    def test_empty_file(self):
        result = _make_extraction("")
        assert len(result.symbols) == 1
        assert result.symbols[0].kind == SymbolKind.MODULE

    def test_file_with_only_imports(self):
        result = _make_extraction("import os\nfrom sys import argv\n")
        assert len(result.symbols) == 1
        assert result.symbols[0].kind == SymbolKind.MODULE

    def test_multiple_decorators(self):
        code = "class Foo:\n    @staticmethod\n    @custom_decorator\n    def create():\n        pass\n"
        result = _make_extraction(code)
        method = next(s for s in result.symbols if s.name == "create")
        assert method.kind == SymbolKind.STATICMETHOD
        assert method.decorators == ("staticmethod", "custom_decorator")

    def test_complex_decorator(self):
        code = "class V:\n    @action(detail=True)\n    def archive(self):\n        pass\n"
        result = _make_extraction(code)
        method = next(s for s in result.symbols if s.name == "archive")
        assert method.kind == SymbolKind.METHOD
        assert "action" in method.decorators
