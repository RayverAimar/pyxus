"""Resolve Python import statements to actual file paths within the repository.

Handles all standard import forms:
- Absolute: ``import os``, ``from os.path import join``
- Relative: ``from . import models``, ``from ..utils import helper``
- Package: ``from wallet_screener.models import Profile`` (following __init__.py re-exports)

External packages (not in the repository) are silently ignored. Unresolvable
internal imports are logged as warnings for the coverage report.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import PurePosixPath

from pyxus.core.file_walker import SourceFile
from pyxus.graph.models import (
    RelationKind,
    Relationship,
    SymbolKind,
    make_relationship_id,
    make_symbol_id,
)

logger = logging.getLogger("pyxus")


@dataclass
class ResolvedImport:
    """An import statement that has been resolved to a file in the repository.

    Attributes:
        source_file: The file that contains the import statement.
        target_file: The resolved file path (relative to repo root).
        imported_names: The specific names imported (empty for ``import module``).
        is_relative: Whether the import used relative syntax (dots).
    """

    source_file: str
    target_file: str
    imported_names: list[str]
    is_relative: bool


@dataclass
class ImportResolutionResult:
    """Complete import resolution output for one or more source files.

    Attributes:
        resolved: Successfully resolved imports with source→target file mapping.
        unresolved: Import statements that couldn't be mapped to a repo file.
        relationships: IMPORTS edges to add to the graph.
    """

    resolved: list[ResolvedImport]
    unresolved: list[str]
    relationships: list[Relationship]


def build_file_index(files: list[SourceFile]) -> dict[str, str]:
    """Build a lookup from module-style dotted path to file path.

    Creates entries for both direct modules and __init__.py packages,
    enabling resolution of imports like ``from wallet_screener.models import X``.

    Example entries:
        "wallet_screener.models" → "wallet_screener/models/__init__.py"
        "wallet_screener.models.profiles" → "wallet_screener/models/profiles.py"
        "utils" → "utils.py"
    """
    index: dict[str, str] = {}
    for f in files:
        path = PurePosixPath(f.path)
        # Convert file path to module dotted path
        parts = list(path.parts)
        if parts[-1] == "__init__.py":
            # Package: wallet_screener/models/__init__.py → "wallet_screener.models"
            module_path = ".".join(parts[:-1])
            if module_path:
                index[module_path] = f.path
        else:
            # Module: wallet_screener/utils.py → "wallet_screener.utils"
            parts[-1] = parts[-1].removesuffix(".py")
            module_path = ".".join(parts)
            index[module_path] = f.path
    return index


def resolve_imports(
    source_file: SourceFile,
    file_index: dict[str, str],
    all_files: dict[str, SourceFile],
) -> ImportResolutionResult:
    """Resolve all import statements in a source file to file paths.

    Args:
        source_file: The file whose imports we're resolving.
        file_index: Dotted module path → file path mapping (from build_file_index).
        all_files: All source files keyed by path, for reading __init__.py re-exports.

    Returns:
        Resolution result with resolved imports, unresolved warnings, and IMPORTS edges.
    """
    try:
        tree = ast.parse(source_file.content, filename=source_file.path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
        return ImportResolutionResult(resolved=[], unresolved=[], relationships=[])

    resolved: list[ResolvedImport] = []
    unresolved: list[str] = []
    relationships: list[Relationship] = []
    seen_targets: set[str] = set()  # Avoid duplicate IMPORTS edges to the same file

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_absolute(alias.name, file_index)
                if target:
                    resolved.append(
                        ResolvedImport(
                            source_file=source_file.path,
                            target_file=target,
                            imported_names=[],
                            is_relative=False,
                        )
                    )
                    if target not in seen_targets:
                        seen_targets.add(target)
                        relationships.append(_make_import_rel(source_file.path, target))
                # External packages are silently ignored

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [alias.name for alias in node.names]
            level = node.level  # Number of dots (0 = absolute)

            if level > 0:
                # Relative import
                target = _resolve_relative(source_file.path, module, level, file_index)
            else:
                # Absolute import
                target = _resolve_absolute(module, file_index)
                if target is None:
                    # Try module.name for each imported name (e.g., from pkg import module)
                    for name in names:
                        sub_target = _resolve_absolute(f"{module}.{name}", file_index)
                        if sub_target and sub_target not in seen_targets:
                            seen_targets.add(sub_target)
                            resolved.append(
                                ResolvedImport(
                                    source_file=source_file.path,
                                    target_file=sub_target,
                                    imported_names=[name],
                                    is_relative=False,
                                )
                            )
                            relationships.append(_make_import_rel(source_file.path, sub_target))
                    continue

            if target:
                resolved.append(
                    ResolvedImport(
                        source_file=source_file.path,
                        target_file=target,
                        imported_names=names,
                        is_relative=level > 0,
                    )
                )
                if target not in seen_targets:
                    seen_targets.add(target)
                    relationships.append(_make_import_rel(source_file.path, target))
            elif level > 0:
                # Relative import that didn't resolve is likely a bug
                import_str = f"{'.' * level}{module}"
                unresolved.append(f"{source_file.path}: from {import_str} import {', '.join(names)}")
                logger.debug("Unresolved relative import in %s: %s", source_file.path, import_str)

    return ImportResolutionResult(
        resolved=resolved,
        unresolved=unresolved,
        relationships=relationships,
    )


def _resolve_absolute(module_dotted: str, file_index: dict[str, str]) -> str | None:
    """Resolve an absolute module path to a file path in the repo.

    Tries the exact module first, then checks if it's a package with __init__.py.
    """
    return file_index.get(module_dotted)


def _resolve_relative(
    source_path: str,
    module: str,
    level: int,
    file_index: dict[str, str],
) -> str | None:
    """Resolve a relative import to a file path.

    ``level`` is the number of dots: ``.`` = 1 (current package),
    ``..`` = 2 (parent package), etc.

    Example: in ``api/serializers/profiles/core.py``:
        ``from ...utils import helper``  →  level=3, module="utils"
        Navigate up 3 directories from the file's package → resolve "utils"
    """
    source = PurePosixPath(source_path)
    # Start from the file's directory (its containing package)
    package_parts = list(source.parts[:-1])

    # Navigate up `level` directories (level=1 stays in current package)
    steps_up = level - 1
    if steps_up > len(package_parts):
        return None  # Can't go above the repo root
    if steps_up > 0:
        package_parts = package_parts[:-steps_up]

    # Build the target module path
    target_module = ".".join(package_parts + module.split(".")) if module else ".".join(package_parts)

    return file_index.get(target_module)


def _make_import_rel(source_path: str, target_path: str) -> Relationship:
    """Create an IMPORTS relationship between two file module symbols."""
    source_id = make_symbol_id(SymbolKind.MODULE, source_path, source_path, 0)
    target_id = make_symbol_id(SymbolKind.MODULE, target_path, target_path, 0)
    return Relationship(
        id=make_relationship_id(source_id, target_id, RelationKind.IMPORTS),
        source_id=source_id,
        target_id=target_id,
        kind=RelationKind.IMPORTS,
    )
