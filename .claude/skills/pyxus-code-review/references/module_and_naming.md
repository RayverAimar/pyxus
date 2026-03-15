# Rule 1: Module Structure and Naming Conventions

Every source module in Pyxus follows a strict ordering and naming convention. Deviations break IDE navigation, confuse developers, and create inconsistency that compounds over time.

## Source module structure (mandatory order)

Every file in `src/pyxus/` must follow this exact order:

```python
"""Module docstring — multi-line, explains purpose and how it fits in the system.

Second paragraph with additional detail if needed.
"""

from __future__ import annotations

import ast                          # 1. Standard library imports
import logging
from dataclasses import dataclass

import rustworkx as rx              # 2. Third-party imports

from pyxus.core.file_walker import SourceFile  # 3. Local imports
from pyxus.graph.models import Symbol

logger = logging.getLogger("pyxus")  # 4. Logger (always this exact form)

MAX_ITERATIONS = 10                  # 5. Constants (UPPER_CASE, with comment)

                                     # 6. Public classes/functions
def extract_symbols(source_file: SourceFile) -> ExtractionResult:
    """Public API function with full docstring."""
    ...

                                     # 7. Private helpers
def _classify_method(decorators: list[str]) -> SymbolKind:
    """Private helper with docstring."""
    ...

class _SymbolVisitor(ast.NodeVisitor):
    """Private class with docstring."""
    ...
```

**Reference file:** `src/pyxus/core/symbol_extractor.py` — the canonical example of correct module structure.

### What to check

1. **Module docstring is multi-line** — explains the purpose AND how it fits in the pipeline. One-liners are insufficient for anything but `__init__.py`.

```python
# BAD
"""Symbol extractor."""

# GOOD
"""Extract Python symbols from source code via AST analysis.

Parses each source file into an AST and walks it to discover all classes,
methods, functions, and properties.
"""
```

2. **`from __future__ import annotations` is present** — Required in ALL source files. NOT required in test files.

3. **Import ordering** — stdlib → third-party → local. Ruff enforces this, but check that local imports use full paths:

```python
# BAD — relative import in src/
from .models import Symbol

# GOOD — absolute import
from pyxus.graph.models import Symbol
```

4. **Logger always uses `"pyxus"`** — Never `__name__`, never a custom string.

```python
# BAD
logger = logging.getLogger(__name__)
logger = logging.getLogger("pyxus.core")

# GOOD
logger = logging.getLogger("pyxus")
```

## Naming conventions

| What | Pattern | Example |
|------|---------|---------|
| Private helper functions | `_snake_case()` | `_classify_method()`, `_resolve_expr()` |
| Private classes | `_ClassName` | `_SymbolVisitor`, `_AssignmentCollector` |
| Constants | `UPPER_CASE` | `MAX_ITERATIONS`, `DEFAULT_EXCLUDES` |
| Data models (graph) | `@dataclass(frozen=True)` | `Symbol`, `Relationship` |
| Result containers | `@dataclass` (mutable) | `ExtractionResult`, `AnalysisStats` |
| ID factory functions | `make_*_id()` | `make_symbol_id()`, `make_relationship_id()` |
| Test builders | `_make_*()` | `_make_store()`, `_make_extraction()` |
| Test extractors | `_extract_*()` | `_extract_resolved_names()` |

### Naming red flags

```python
# BAD — wrong prefix for private helper
def classify_method(decorators):  # Missing _ prefix for private function
def createSymbol(kind, name):     # camelCase — must be snake_case
class symbolVisitor:              # lowercase class — must be PascalCase

# GOOD
def _classify_method(decorators: list[str]) -> SymbolKind:
def _create_symbol(kind: SymbolKind, name: str) -> Symbol:
class _SymbolVisitor(ast.NodeVisitor):
```

## Section separators

Files with 3+ distinct logical sections should use section separators:

```python
# ── Mutations ─────────────────────────────────────────────────────────

def add_symbol(self, symbol: Symbol) -> int:
    ...

# ── Lookups ───────────────────────────────────────────────────────────

def get_symbol(self, symbol_id: str) -> Symbol | None:
    ...
```

**When to use:** Files >100 lines with distinct logical groupings (e.g., `store.py`, `call_resolver.py`, `analyzer.py`).
**When NOT to use:** Small files, files with a single flow (e.g., `ast_utils.py`, `heritage.py`).

**Reference files with separators:** `store.py` (5 sections), `call_resolver.py` (4 sections), `analyzer.py` (3 sections), `queries.py` (2 sections).

## Docstring conventions

### Module docstrings

```python
# BAD — too short, doesn't explain how it fits
"""File walker module."""

# GOOD — explains purpose and connection to the system
"""Repository file discovery for Python source files.

Discovers all .py files in a repository while respecting .gitignore rules
and excluding common non-source directories (virtualenvs, caches, migrations).
Uses ``git ls-files`` when available for accurate .gitignore handling,
falling back to manual directory traversal otherwise.
"""
```

### Function docstrings

```python
# Public functions — full docstring
def resolve_calls(
    files: list[SourceFile],
    graph: GraphStore,
    class_hierarchy: ClassHierarchy,
) -> CallResolutionResult:
    """Resolve all function/method calls using assignment graph analysis.

    Runs the fixed-point iteration over all source files, then extracts CALLS edges.
    """

# Private helpers — 1-line docstring
def _classify_method(decorators: list[str]) -> SymbolKind:
    """Determine the SymbolKind for a function defined inside a class."""
```

### Comments

- Comments explain "why", not "what"
- No dead references (task IDs like CR-008, review tickets, TODO with names)
- Constants should have a comment explaining thresholds:

```python
# BAD
MAX_ITERATIONS = 10

# GOOD
# Typical codebases converge in 2-4 iterations; 10 is a safe upper bound
# that prevents runaway loops on pathological assignment cycles.
MAX_ITERATIONS = 10
```

## How to search

When reviewing a new source file:
1. Find the 2-3 most similar existing files (same directory, same purpose)
2. Compare module structure order, import style, naming pattern
3. If they don't match, flag it with the correct pattern from the reference file
