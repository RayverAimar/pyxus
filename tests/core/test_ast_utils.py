"""Tests for core/ast_utils.py."""

import ast

from pyxus.core.ast_utils import get_base_name, get_dotted_name


def _make_expr(code: str) -> ast.expr:
    """Parse a single expression from code."""
    tree = ast.parse(code, mode="eval")
    return tree.body


class TestGetDottedName:
    def test_simple_name(self):
        assert get_dotted_name(_make_expr("foo")) == "foo"

    def test_attribute(self):
        assert get_dotted_name(_make_expr("foo.bar")) == "foo.bar"

    def test_nested_attribute(self):
        assert get_dotted_name(_make_expr("a.b.c")) == "a.b.c"

    def test_call_strips_to_function_name(self):
        assert get_dotted_name(_make_expr("decorator()")) == "decorator"

    def test_call_with_dotted_name(self):
        assert get_dotted_name(_make_expr("app.route('/path')")) == "app.route"

    def test_unsupported_returns_none(self):
        assert get_dotted_name(_make_expr("1 + 2")) is None

    def test_subscript_returns_none(self):
        assert get_dotted_name(_make_expr("list[int]")) is None


class TestGetBaseName:
    def test_simple_name(self):
        assert get_base_name(_make_expr("Parent")) == "Parent"

    def test_dotted_name(self):
        assert get_base_name(_make_expr("module.Parent")) == "module.Parent"

    def test_call_returns_none(self):
        """Base classes via function calls (e.g., type()) are not supported."""
        assert get_base_name(_make_expr("type('Base', (), {})")) is None

    def test_subscript_returns_none(self):
        """Generic[T] style bases are not supported."""
        assert get_base_name(_make_expr("Generic[T]")) is None
