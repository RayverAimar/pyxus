"""Extract Python symbols from source code via AST analysis.

Parses each source file into an AST and walks it to discover all classes,
methods, functions, and properties. For each symbol found, produces a
Symbol node and the structural relationships that connect it to its
containing scope (DEFINES for file→symbol, HAS_METHOD for class→method).
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass

from pyxus.core.ast_utils import get_dotted_name
from pyxus.core.file_walker import SourceFile
from pyxus.graph.models import (
    RelationKind,
    Relationship,
    Symbol,
    SymbolKind,
    make_relationship_id,
    make_symbol_id,
)

logger = logging.getLogger("pyxus")


@dataclass
class ExtractionResult:
    """The output of extracting symbols from a single source file.

    Attributes:
        symbols: All Symbol nodes discovered in the file.
        relationships: Structural edges — DEFINES (module→symbol) and
                       HAS_METHOD (class→method/property).
    """

    symbols: list[Symbol]
    relationships: list[Relationship]


def extract_symbols(source_file: SourceFile) -> ExtractionResult:
    """Parse a Python file and extract all symbols with their relationships.

    Returns an empty ExtractionResult if the file has a syntax error.
    """
    try:
        tree = ast.parse(source_file.content, filename=source_file.path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
        return ExtractionResult(symbols=[], relationships=[])

    visitor = _SymbolVisitor(source_file.path)
    visitor.visit(tree)
    return ExtractionResult(symbols=visitor.symbols, relationships=visitor.relationships)


def _classify_method(decorators: list[str]) -> SymbolKind:
    """Determine the SymbolKind for a function defined inside a class.

    Priority: @staticmethod > @classmethod > @property > plain method.
    This matches Python's semantics where these decorators are mutually
    exclusive in practice.
    """
    if "staticmethod" in decorators:
        return SymbolKind.STATICMETHOD
    if "classmethod" in decorators:
        return SymbolKind.CLASSMETHOD
    if "property" in decorators:
        return SymbolKind.PROPERTY
    return SymbolKind.METHOD


class _SymbolVisitor(ast.NodeVisitor):
    """Walks a Python AST and collects symbols and structural relationships.

    Maintains a stack of enclosing class names to distinguish between
    top-level functions and methods defined inside a class body.
    """

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.symbols: list[Symbol] = []
        self.relationships: list[Relationship] = []
        # Stack of enclosing ClassDef symbol IDs — non-empty means we're inside a class
        self._class_stack: list[str] = []

        # Create the MODULE symbol that represents this file
        self._module_id = make_symbol_id(SymbolKind.MODULE, file_path, file_path, 0)
        self.symbols.append(
            Symbol(
                id=self._module_id,
                name=file_path,
                kind=SymbolKind.MODULE,
                file_path=file_path,
                start_line=0,
                end_line=0,
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Extract a CLASS symbol and visit its body for methods."""
        decorators = [get_dotted_name(d) or "<unknown>" for d in node.decorator_list]
        symbol_id = make_symbol_id(SymbolKind.CLASS, self.file_path, node.name, node.lineno)

        symbol = Symbol(
            id=symbol_id,
            name=node.name,
            kind=SymbolKind.CLASS,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            decorators=tuple(decorators),
            is_exported=not node.name.startswith("_"),
        )
        self.symbols.append(symbol)

        # DEFINES edge: parent scope → class
        parent_id = self._class_stack[-1] if self._class_stack else self._module_id
        rel_kind = RelationKind.HAS_METHOD if self._class_stack else RelationKind.DEFINES
        self.relationships.append(
            Relationship(
                id=make_relationship_id(parent_id, symbol_id, rel_kind),
                source_id=parent_id,
                target_id=symbol_id,
                kind=rel_kind,
            )
        )

        # Visit class body with this class on the stack
        self._class_stack.append(symbol_id)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract a function or method symbol depending on enclosing scope."""
        decorators = [get_dotted_name(d) or "<unknown>" for d in node.decorator_list]
        inside_class = bool(self._class_stack)

        kind = _classify_method(decorators) if inside_class else SymbolKind.FUNCTION

        symbol_id = make_symbol_id(kind, self.file_path, node.name, node.lineno)

        symbol = Symbol(
            id=symbol_id,
            name=node.name,
            kind=kind,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            decorators=tuple(decorators),
            is_exported=not node.name.startswith("_"),
        )
        self.symbols.append(symbol)

        if inside_class:
            # HAS_METHOD edge: enclosing class → this method
            class_id = self._class_stack[-1]
            self.relationships.append(
                Relationship(
                    id=make_relationship_id(class_id, symbol_id, RelationKind.HAS_METHOD),
                    source_id=class_id,
                    target_id=symbol_id,
                    kind=RelationKind.HAS_METHOD,
                )
            )
        else:
            # DEFINES edge: module → this function
            self.relationships.append(
                Relationship(
                    id=make_relationship_id(self._module_id, symbol_id, RelationKind.DEFINES),
                    source_id=self._module_id,
                    target_id=symbol_id,
                    kind=RelationKind.DEFINES,
                )
            )

    # async def is handled identically to def
    visit_AsyncFunctionDef = visit_FunctionDef
