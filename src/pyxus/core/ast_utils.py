"""Shared AST helper functions used across multiple core modules.

Provides a single implementation of recurring AST patterns — extracting
dotted names from expressions, getting decorator names, and building
attribute chains — so that symbol_extractor, heritage, and call_resolver
don't each maintain their own copy of the same recursive logic.
"""

from __future__ import annotations

import ast


def get_dotted_name(node: ast.expr) -> str | None:
    """Recursively build a dotted name from an AST expression.

    Handles the three common patterns:
    - ``ast.Name("foo")`` → ``"foo"``
    - ``ast.Attribute(Name("foo"), "bar")`` → ``"foo.bar"``
    - ``ast.Call(Name("decorator"), ...)`` → ``"decorator"`` (strips the call)

    Returns None for complex expressions that don't reduce to a name
    (e.g., subscripts, binary ops).
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = get_dotted_name(node.value)
        if prefix:
            return f"{prefix}.{node.attr}"
    if isinstance(node, ast.Call):
        return get_dotted_name(node.func)
    return None


def get_base_name(node: ast.expr) -> str | None:
    """Extract a class name from a base class AST node.

    Like ``get_dotted_name`` but without the ``ast.Call`` branch — base classes
    specified via function calls (e.g., ``type("Base", (), {})``) are not
    supported and return None.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = get_base_name(node.value)
        if prefix:
            return f"{prefix}.{node.attr}"
    return None
