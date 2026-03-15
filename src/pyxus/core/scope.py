"""Scope resolution using Python's symtable module.

NOTE: This module is fully implemented and tested but not yet integrated
into the analysis pipeline. It will be wired into call_resolver to improve
resolution accuracy by filtering local-variable false matches.

Builds a tree of scopes from source code to determine where each identifier
is defined and visible. This information feeds into the call resolver's
assignment graph: knowing whether a name is local, imported, or global
determines how its assignments propagate.

Scope hierarchy example:
    Module scope
    ├── Class scope (ProfileService)
    │   ├── Method scope (create) → local variables
    │   └── Method scope (update) → local variables
    └── Function scope (helper_func) → local variables
"""

from __future__ import annotations

import logging
import symtable as symtable_mod
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger("pyxus")

__all__ = ["ScopeInfo", "ScopeTree", "ScopeType", "SymbolCategory"]


class ScopeType(StrEnum):
    """Type of a Python scope."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"


class SymbolCategory(StrEnum):
    """How a symbol is bound in its scope."""

    IMPORTED = "imported"
    PARAMETER = "parameter"
    LOCAL = "local"
    GLOBAL = "global"
    FREE = "free"
    REFERENCED = "referenced"
    UNKNOWN = "unknown"


@dataclass
class ScopeInfo:
    """Information about a single scope (module, class, or function).

    Attributes:
        name: The scope's name (function name, class name, or "top" for module).
        scope_type: One of "module", "class", or "function".
        symbols: Names defined or referenced in this scope, with their category.
        children: Nested scopes (methods inside classes, closures, etc.).
    """

    name: str
    scope_type: ScopeType
    symbols: dict[str, SymbolCategory] = field(default_factory=dict)
    children: list[ScopeInfo] = field(default_factory=list)


class ScopeTree:
    """Wraps Python's symtable to provide scope resolution for analysis.

    Constructed from source code, it answers questions like:
    - "Is 'profile' a local variable in function 'create'?"
    - "Is 'ProfileService' an imported name in this module?"
    - "What names are imported at the module level?"
    """

    def __init__(self, root: ScopeInfo, imported_names: set[str]) -> None:
        self._root = root
        self._imported_names = imported_names
        # Flat index: scope_name → ScopeInfo for fast lookup
        self._scope_index: dict[str, ScopeInfo] = {}
        self._build_index(self._root)

    @classmethod
    def from_source(cls, source: str, filename: str = "<string>") -> ScopeTree | None:
        """Build a scope tree from Python source code.

        Returns None if the source has a syntax error.
        """
        try:
            table = symtable_mod.symtable(source, filename, "exec")
        except SyntaxError:
            logger.warning("Cannot build scope tree for %s (syntax error)", filename)
            return None

        imported_names: set[str] = set()
        root = cls._process_table(table, imported_names)
        return cls(root, imported_names)

    @classmethod
    def _process_table(cls, table: symtable_mod.SymbolTable, imported_names: set[str]) -> ScopeInfo:
        """Recursively convert a symtable.SymbolTable into our ScopeInfo tree."""
        scope_type = _classify_table(table)
        info = ScopeInfo(name=table.get_name(), scope_type=scope_type)

        for sym in table.get_symbols():
            category = _classify_symbol(sym)
            info.symbols[sym.get_name()] = category
            if sym.is_imported():
                imported_names.add(sym.get_name())

        for child_table in table.get_children():
            child_info = cls._process_table(child_table, imported_names)
            info.children.append(child_info)

        return info

    def _build_index(self, scope: ScopeInfo) -> None:
        """Flatten the scope tree into a lookup dict."""
        self._scope_index[scope.name] = scope
        for child in scope.children:
            self._build_index(child)

    def get_scope(self, name: str) -> ScopeInfo | None:
        """Look up a scope by name (function name, class name, etc.)."""
        return self._scope_index.get(name)

    def get_imports(self) -> set[str]:
        """Get all names that were imported at the module level."""
        return set(self._imported_names)

    def is_local(self, name: str, scope_name: str) -> bool:
        """Check if a name is a local variable in the given scope."""
        scope = self._scope_index.get(scope_name)
        if scope is None:
            return False
        return scope.symbols.get(name) == SymbolCategory.LOCAL

    def is_imported(self, name: str) -> bool:
        """Check if a name was brought in via an import statement."""
        return name in self._imported_names

    def classify_name(self, name: str, scope_name: str) -> SymbolCategory:
        """Determine how a name is bound in a given scope."""
        scope = self._scope_index.get(scope_name)
        if scope is not None and name in scope.symbols:
            return scope.symbols[name]
        if name in self._root.symbols:
            return self._root.symbols[name]
        return SymbolCategory.UNKNOWN

    @property
    def root(self) -> ScopeInfo:
        """The module-level scope."""
        return self._root


def _classify_table(table: symtable_mod.SymbolTable) -> ScopeType:
    """Map symtable table type to ScopeType."""
    table_type = table.get_type()
    if table_type == "module":
        return ScopeType.MODULE
    if table_type == "class":
        return ScopeType.CLASS
    return ScopeType.FUNCTION


def _classify_symbol(sym: symtable_mod.Symbol) -> SymbolCategory:
    """Determine the binding category of a symbol in its scope."""
    if sym.is_imported():
        return SymbolCategory.IMPORTED
    if sym.is_parameter():
        return SymbolCategory.PARAMETER
    if sym.is_local():
        return SymbolCategory.LOCAL
    if sym.is_declared_global():
        return SymbolCategory.GLOBAL
    if sym.is_free():
        return SymbolCategory.FREE
    return SymbolCategory.REFERENCED
