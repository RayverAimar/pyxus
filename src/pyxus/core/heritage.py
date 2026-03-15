"""Class inheritance extraction and Method Resolution Order (MRO) computation.

Extracts base class names from class definitions by inspecting ClassDef.bases
in the AST. Also provides a ClassHierarchy structure that computes the C3
linearization (MRO) for attribute resolution — critical for the call resolver
to determine which class defines a method when called via ``self.method()``
or ``obj.method()``.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

from pyxus.core.ast_utils import get_base_name
from pyxus.core.file_walker import SourceFile

logger = logging.getLogger("pyxus")


@dataclass
class HeritageResult:
    """Inheritance information extracted from a source file.

    Attributes:
        class_bases: Mapping of class name → list of base class names, used
                     to build the ClassHierarchy after all files are processed.
    """

    class_bases: dict[str, list[str]]


def extract_heritage(source_file: SourceFile) -> HeritageResult:
    """Extract base class names from class definitions in a source file.

    Handles:
    - Simple inheritance: ``class Child(Parent)``
    - Multiple inheritance: ``class Child(Parent1, Parent2)``
    - Qualified bases: ``class Child(module.Parent)``
    - Skips non-name bases like ``class Meta(type("Base", (), {}))``
    """
    try:
        tree = ast.parse(source_file.content, filename=source_file.path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
        return HeritageResult(class_bases={})

    visitor = _HeritageVisitor()
    visitor.visit(tree)
    return HeritageResult(class_bases=visitor.class_bases)


class _HeritageVisitor(ast.NodeVisitor):
    """Walks the AST to extract class inheritance information."""

    def __init__(self) -> None:
        self.class_bases: dict[str, list[str]] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = []
        for base_node in node.bases:
            base_name = get_base_name(base_node)
            if base_name and base_name != "object":
                bases.append(base_name)

        if bases:
            self.class_bases[node.name] = bases

        self.generic_visit(node)


class ClassHierarchy:
    """Maintains class inheritance relationships and computes MRO.

    Built incrementally as files are analyzed, then used by the call
    resolver to determine which class in the inheritance chain defines
    a given attribute (method, property, etc.).
    """

    def __init__(self) -> None:
        self._bases: dict[str, list[str]] = {}
        self._attributes: dict[str, set[str]] = {}

    def add_class(self, class_id: str, base_ids: list[str]) -> None:
        """Register a class and its direct base classes."""
        self._bases[class_id] = base_ids

    def add_attribute(self, class_id: str, attr_name: str) -> None:
        """Register an attribute (method, property) defined on a class."""
        if class_id not in self._attributes:
            self._attributes[class_id] = set()
        self._attributes[class_id].add(attr_name)

    def get_mro(self, class_id: str) -> list[str]:
        """Compute the Method Resolution Order using C3 linearization.

        Falls back to DFS if C3 fails (inconsistent hierarchies).
        """
        try:
            return self._c3_linearize(class_id)
        except ValueError:
            logger.warning("C3 linearization failed for %s, using DFS fallback", class_id)
            return self._dfs_mro(class_id)

    def resolve_attribute(self, class_id: str, attr_name: str) -> str | None:
        """Find which class in the MRO defines the given attribute.

        Walks the MRO from the class itself upward through its bases,
        returning the first class that defines it. Returns None if not found.
        """
        for cid in self.get_mro(class_id):
            if attr_name in self._attributes.get(cid, set()):
                return cid
        return None

    def get_bases(self, class_id: str) -> list[str]:
        """Get the direct base class IDs for a given class."""
        return self._bases.get(class_id, [])

    def _c3_linearize(self, class_id: str) -> list[str]:
        """C3 linearization — the same algorithm Python uses for MRO."""
        if class_id not in self._bases or not self._bases[class_id]:
            return [class_id]

        base_mros = [self._c3_linearize(base) for base in self._bases[class_id]]
        base_mros.append(list(self._bases[class_id]))

        result = [class_id]
        while any(base_mros):
            candidate = None
            for mro in base_mros:
                if not mro:
                    continue
                head = mro[0]
                in_tail = any(head in other[1:] for other in base_mros if other)
                if not in_tail:
                    candidate = head
                    break

            if candidate is None:
                raise ValueError(f"Inconsistent hierarchy for {class_id}")

            result.append(candidate)
            base_mros = [[c for c in mro if c != candidate] for mro in base_mros]

        return result

    def _dfs_mro(self, class_id: str) -> list[str]:
        """Simple depth-first MRO as a fallback when C3 fails."""
        visited = []
        stack = [class_id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            visited.append(current)
            for base in reversed(self._bases.get(current, [])):
                if base not in seen:
                    stack.append(base)
        return visited
