"""Tests for core/heritage.py."""

from pyxus.core.file_walker import SourceFile
from pyxus.core.heritage import ClassHierarchy, extract_heritage


def _make_heritage(code: str, path: str = "test.py"):
    """Extract heritage information from a code string for testing."""
    sf = SourceFile(path=path, absolute_path=f"/tmp/{path}", content=code)
    return extract_heritage(sf)


class TestExtractHeritage:
    def test_simple_inheritance(self):
        result = _make_heritage("class Child(Parent):\n    pass\n")
        assert result.class_bases == {"Child": ["Parent"]}

    def test_multiple_inheritance(self):
        result = _make_heritage("class Child(Base1, Base2):\n    pass\n")
        assert result.class_bases == {"Child": ["Base1", "Base2"]}

    def test_qualified_base(self):
        result = _make_heritage("class MyView(views.View):\n    pass\n")
        assert result.class_bases == {"MyView": ["views.View"]}

    def test_skips_object_base(self):
        """object is implicit — no need to track it."""
        result = _make_heritage("class Foo(object):\n    pass\n")
        assert result.class_bases == {}

    def test_no_bases(self):
        result = _make_heritage("class Standalone:\n    pass\n")
        assert result.class_bases == {}

    def test_syntax_error_returns_empty(self):
        result = _make_heritage("class Broken(\n")
        assert result.class_bases == {}

    def test_nested_class_heritage(self):
        code = "class Outer:\n    class Inner(Base):\n        pass\n"
        result = _make_heritage(code)
        assert "Inner" in result.class_bases
        assert result.class_bases["Inner"] == ["Base"]


class TestClassHierarchy:
    def test_simple_mro(self):
        h = ClassHierarchy()
        h.add_class("Child", ["Parent"])
        h.add_class("Parent", [])
        assert h.get_mro("Child") == ["Child", "Parent"]

    def test_no_bases_mro(self):
        h = ClassHierarchy()
        h.add_class("Standalone", [])
        assert h.get_mro("Standalone") == ["Standalone"]

    def test_multiple_inheritance_mro(self):
        """Classic diamond: D(B, C), B(A), C(A)."""
        h = ClassHierarchy()
        h.add_class("A", [])
        h.add_class("B", ["A"])
        h.add_class("C", ["A"])
        h.add_class("D", ["B", "C"])
        mro = h.get_mro("D")
        # C3 linearization: D → B → C → A
        assert mro == ["D", "B", "C", "A"]

    def test_c3_three_levels(self):
        h = ClassHierarchy()
        h.add_class("A", [])
        h.add_class("B", ["A"])
        h.add_class("C", ["B"])
        assert h.get_mro("C") == ["C", "B", "A"]

    def test_unknown_class_returns_self_only(self):
        """A class not registered should return just itself."""
        h = ClassHierarchy()
        assert h.get_mro("Unknown") == ["Unknown"]

    def test_base_not_registered(self):
        """If a base class isn't registered, MRO should still work."""
        h = ClassHierarchy()
        h.add_class("Child", ["MissingBase"])
        mro = h.get_mro("Child")
        assert "Child" in mro


class TestResolveAttribute:
    def test_attribute_on_class_itself(self):
        h = ClassHierarchy()
        h.add_class("Foo", [])
        h.add_attribute("Foo", "bar")
        assert h.resolve_attribute("Foo", "bar") == "Foo"

    def test_attribute_on_parent(self):
        h = ClassHierarchy()
        h.add_class("Parent", [])
        h.add_class("Child", ["Parent"])
        h.add_attribute("Parent", "save")
        assert h.resolve_attribute("Child", "save") == "Parent"

    def test_attribute_overridden_in_child(self):
        """Child's definition should shadow parent's."""
        h = ClassHierarchy()
        h.add_class("Parent", [])
        h.add_class("Child", ["Parent"])
        h.add_attribute("Parent", "save")
        h.add_attribute("Child", "save")
        assert h.resolve_attribute("Child", "save") == "Child"

    def test_attribute_not_found(self):
        h = ClassHierarchy()
        h.add_class("Foo", [])
        assert h.resolve_attribute("Foo", "nonexistent") is None

    def test_diamond_resolution(self):
        """In diamond D(B,C) where both B and C define 'x', B wins (MRO order)."""
        h = ClassHierarchy()
        h.add_class("A", [])
        h.add_class("B", ["A"])
        h.add_class("C", ["A"])
        h.add_class("D", ["B", "C"])
        h.add_attribute("B", "process")
        h.add_attribute("C", "process")
        # B comes before C in D's MRO
        assert h.resolve_attribute("D", "process") == "B"

    def test_get_bases(self):
        h = ClassHierarchy()
        h.add_class("Child", ["Base1", "Base2"])
        assert h.get_bases("Child") == ["Base1", "Base2"]
        assert h.get_bases("Unknown") == []


class TestDfsFallback:
    def test_inconsistent_hierarchy_uses_dfs(self):
        """When C3 fails, the DFS fallback should still return a valid MRO."""
        h = ClassHierarchy()
        # Create an inconsistent hierarchy that violates C3:
        # X(A, B), Y(B, A) — then Z(X, Y) can't be linearized with C3
        h.add_class("A", [])
        h.add_class("B", [])
        h.add_class("X", ["A", "B"])
        h.add_class("Y", ["B", "A"])
        h.add_class("Z", ["X", "Y"])

        mro = h.get_mro("Z")
        assert mro[0] == "Z"
        assert "X" in mro
        assert "Y" in mro
        assert "A" in mro
        assert "B" in mro

    def test_dfs_mro_handles_deep_chain(self):
        h = ClassHierarchy()
        h.add_class("A", [])
        h.add_class("B", ["A"])
        h.add_class("C", ["B"])
        h.add_class("D", ["C"])

        # Force DFS by creating inconsistent hierarchy on separate branch
        h.add_class("E", [])
        h.add_class("F", ["A", "E"])
        h.add_class("G", ["E", "A"])
        h.add_class("H", ["F", "G"])

        mro = h.get_mro("H")
        assert mro[0] == "H"
        assert "F" in mro
