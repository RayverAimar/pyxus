"""Core data models for the Pyxus knowledge graph.

Defines the fundamental types that represent nodes (Symbols) and edges
(Relationships) in the code knowledge graph. All models are immutable
frozen dataclasses to ensure graph consistency and hashability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "CallReason",
    "RelationKind",
    "Relationship",
    "RiskLevel",
    "Symbol",
    "SymbolKind",
    "make_relationship_id",
    "make_symbol_id",
]


class SymbolKind(StrEnum):
    """Classification of Python symbols extracted from source code.

    Each kind maps to a specific AST construct:
    - MODULE: a .py file (one per source file)
    - CLASS: a class definition (ClassDef)
    - METHOD: a function defined inside a class body
    - FUNCTION: a top-level function (not inside a class)
    - PROPERTY: a method decorated with @property
    - CLASSMETHOD: a method decorated with @classmethod
    - STATICMETHOD: a method decorated with @staticmethod
    """

    MODULE = "module"
    CLASS = "class"
    METHOD = "method"
    FUNCTION = "function"
    PROPERTY = "property"
    CLASSMETHOD = "classmethod"
    STATICMETHOD = "staticmethod"


class RelationKind(StrEnum):
    """Types of relationships between symbols in the knowledge graph.

    Core Python relationships capture the structural and behavioral
    connections between symbols discovered through static analysis.
    """

    DEFINES = "defines"
    HAS_METHOD = "has_method"
    CALLS = "calls"
    IMPORTS = "imports"
    EXTENDS = "extends"


class CallReason(StrEnum):
    """Classification of why a call could not be resolved."""

    EXTERNAL = "external"
    UNRESOLVED_INTERNAL = "unresolved_internal"


class RiskLevel(StrEnum):
    """Risk classification for blast radius analysis."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Symbol:
    """A named code entity extracted from Python source.

    Represents a single identifiable unit in the codebase: a module, class,
    function, method, or property. Frozen to guarantee immutability once
    added to the graph.

    Attributes:
        id: Deterministic identifier. Format: "{kind}:{file_path}:{name}:{line}".
        name: The symbol's Python name (e.g., "ProfileService").
        kind: What type of Python construct this symbol represents.
        file_path: Relative path from the repository root.
        start_line: First line of the definition in source.
        end_line: Last line of the definition in source.
        decorators: Decorator names applied to this symbol, as a tuple for hashability.
        is_exported: False if the name starts with underscore (private by convention).
        metadata: Extensible dict for framework-specific data. Excluded from
                  equality checks and hashing to allow annotation without
                  affecting identity.
    """

    id: str
    name: str
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    decorators: tuple[str, ...] = ()
    is_exported: bool = True
    metadata: dict = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True)
class Relationship:
    """A directed edge between two symbols in the knowledge graph.

    Captures a specific relationship from a source symbol to a target symbol,
    such as "function A calls function B" or "class C extends class D".

    Attributes:
        id: Deterministic identifier. Format: "{kind}:{source_id}->{target_id}".
        source_id: Symbol ID of the edge origin.
        target_id: Symbol ID of the edge destination.
        kind: What type of relationship this edge represents.
        confidence: How certain we are about this relationship (0.0 to 1.0).
                    Direct observations (e.g., explicit imports) are 1.0;
                    inferred relationships (e.g., assignment-graph call
                    resolution) may be lower.
        metadata: Extensible dict for additional context (e.g., {"reason": "import-resolved"}).
                  Excluded from equality checks and hashing.
    """

    id: str
    source_id: str
    target_id: str
    kind: RelationKind
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict, hash=False, compare=False)


def make_symbol_id(kind: SymbolKind, file_path: str, name: str, line: int) -> str:
    """Generate a deterministic symbol ID from its defining attributes.

    The same inputs always produce the same ID, enabling stable references
    across incremental re-analysis runs.

    Example:
        >>> make_symbol_id(SymbolKind.CLASS, "services/profiles.py", "ProfileService", 42)
        "class:services/profiles.py:ProfileService:42"
    """
    return f"{kind.value}:{file_path}:{name}:{line}"


def make_relationship_id(source_id: str, target_id: str, kind: RelationKind) -> str:
    """Generate a deterministic relationship ID from source, target, and kind.

    Example:
        >>> make_relationship_id("class:f.py:A:1", "class:f.py:B:5", RelationKind.EXTENDS)
        "extends:class:f.py:A:1->class:f.py:B:5"
    """
    return f"{kind.value}:{source_id}->{target_id}"
