"""Tests for core/scope.py."""

from pyxus.core.scope import ScopeTree


class TestScopeTreeFromSource:
    def test_builds_from_valid_source(self):
        tree = ScopeTree.from_source("x = 1\n")
        assert tree is not None
        assert tree.root.scope_type == "module"

    def test_returns_none_on_syntax_error(self):
        tree = ScopeTree.from_source("def broken(:\n")
        assert tree is None

    def test_detects_module_scope(self):
        tree = ScopeTree.from_source("x = 1\ndef foo(): pass\n")
        assert tree.root.scope_type == "module"


class TestImportDetection:
    def test_detects_import(self):
        tree = ScopeTree.from_source("import os\n")
        assert tree.is_imported("os")

    def test_detects_from_import(self):
        tree = ScopeTree.from_source("from os.path import join\n")
        assert tree.is_imported("join")

    def test_non_import_not_detected(self):
        tree = ScopeTree.from_source("x = 1\n")
        assert not tree.is_imported("x")

    def test_get_imports(self):
        tree = ScopeTree.from_source("import os\nfrom sys import argv\nx = 1\n")
        imports = tree.get_imports()
        assert "os" in imports
        assert "argv" in imports
        assert "x" not in imports


class TestLocalDetection:
    def test_local_variable(self):
        code = "def foo():\n    x = 1\n"
        tree = ScopeTree.from_source(code)
        assert tree.is_local("x", "foo")

    def test_parameter_is_not_local(self):
        """Parameters are classified separately from locals."""
        code = "def foo(x):\n    pass\n"
        tree = ScopeTree.from_source(code)
        # x is a parameter, not a "local" in our classification
        assert not tree.is_local("x", "foo")

    def test_module_var_not_local_to_function(self):
        code = "x = 1\ndef foo():\n    y = 2\n"
        tree = ScopeTree.from_source(code)
        assert not tree.is_local("x", "foo")


class TestClassifyName:
    def test_classify_parameter(self):
        code = "def foo(x):\n    pass\n"
        tree = ScopeTree.from_source(code)
        assert tree.classify_name("x", "foo") == "parameter"

    def test_classify_local(self):
        code = "def foo():\n    x = 1\n"
        tree = ScopeTree.from_source(code)
        assert tree.classify_name("x", "foo") == "local"

    def test_classify_imported(self):
        code = "import os\n"
        tree = ScopeTree.from_source(code)
        assert tree.classify_name("os", "top") == "imported"

    def test_classify_unknown(self):
        code = "x = 1\n"
        tree = ScopeTree.from_source(code)
        assert tree.classify_name("nonexistent", "nonexistent_scope") == "unknown"


class TestNestedScopes:
    def test_class_scope(self):
        code = "class Foo:\n    x = 1\n    def bar(self):\n        y = 2\n"
        tree = ScopeTree.from_source(code)
        foo_scope = tree.get_scope("Foo")
        assert foo_scope is not None
        assert foo_scope.scope_type == "class"

    def test_method_scope(self):
        code = "class Foo:\n    def bar(self):\n        y = 2\n"
        tree = ScopeTree.from_source(code)
        bar_scope = tree.get_scope("bar")
        assert bar_scope is not None
        assert bar_scope.scope_type == "function"

    def test_closure_free_variable(self):
        code = "def outer():\n    x = 1\n    def inner():\n        return x\n"
        tree = ScopeTree.from_source(code)
        assert tree.classify_name("x", "inner") == "free"

    def test_global_variable(self):
        code = "x = 1\ndef foo():\n    global x\n    x = 2\n"
        tree = ScopeTree.from_source(code)
        assert tree.classify_name("x", "foo") == "global"

    def test_get_scope_nonexistent(self):
        tree = ScopeTree.from_source("x = 1\n")
        assert tree.get_scope("nonexistent") is None

    def test_root_property(self):
        tree = ScopeTree.from_source("x = 1\n")
        assert tree.root.scope_type == "module"

    def test_is_local_nonexistent_scope(self):
        tree = ScopeTree.from_source("x = 1\n")
        assert tree.is_local("x", "nonexistent") is False

    def test_classify_referenced_name(self):
        """A name used but not assigned should be classified as 'referenced'."""
        code = "def foo():\n    print(undefined_var)\n"
        tree = ScopeTree.from_source(code)
        # 'undefined_var' is used but never defined — should be referenced
        assert tree.classify_name("undefined_var", "foo") == "referenced"

    def test_classify_falls_back_to_module_scope(self):
        """If name not in requested scope, fall back to module-level."""
        code = "import os\ndef foo():\n    pass\n"
        tree = ScopeTree.from_source(code)
        # 'os' is imported at module level, not inside 'foo'
        assert tree.classify_name("os", "foo") == "imported"
