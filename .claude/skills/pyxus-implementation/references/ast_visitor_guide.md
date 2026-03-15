# How to: Create a New AST Analyzer

This guide covers how to create a new module that analyzes Python source code via AST. Use this for: Django plugin modules, new symbol detection, decorator analysis, etc.

## Step-by-step template

### 1. Create the source file

File: `src/pyxus/plugins/django/signals.py` (or wherever it belongs)

```python
"""Detect Django signal receivers and connect() calls.

Parses @receiver(signal, sender=Model) decorators and signal.connect(handler)
calls to build RECEIVES_SIGNAL relationships in the knowledge graph.
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
    make_relationship_id,
)
from pyxus.graph.store import GraphStore

logger = logging.getLogger("pyxus")


@dataclass
class SignalResult:
    """Signal relationships discovered in a single source file."""

    relationships: list[Relationship]


def detect_signals(source_file: SourceFile, graph: GraphStore) -> SignalResult:
    """Detect signal receivers in a Python source file.

    Returns an empty SignalResult if the file has a syntax error.
    """
    try:
        tree = ast.parse(source_file.content, filename=source_file.path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
        return SignalResult(relationships=[])

    visitor = _SignalVisitor(source_file.path, graph)
    visitor.visit(tree)
    return SignalResult(relationships=visitor.relationships)


class _SignalVisitor(ast.NodeVisitor):
    """Walks the AST to find signal receiver patterns."""

    def __init__(self, file_path: str, graph: GraphStore) -> None:
        self.file_path = file_path
        self.graph = graph
        self.relationships: list[Relationship] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check decorators for @receiver(signal, sender=Model)."""
        for decorator in node.decorator_list:
            # ... analyze decorator ...
            pass
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef
```

### 2. Key patterns to follow

**From `symbol_extractor.py`:**
- Public function as entry point: `detect_signals(source_file, graph) -> SignalResult`
- Private visitor class: `_SignalVisitor(ast.NodeVisitor)`
- SyntaxError returns empty result, never None
- Results collected on visitor instance, returned by public function

**From `call_resolver.py` (if you need namespace tracking):**
- Extend `_NamespaceTrackingVisitor` for scope-aware visitors
- Use `self._current_ns` for the current namespace path
- Push/pop `_class_stack` and `_ns_stack` in visit methods

### 3. Integrate into the pipeline

In `analyzer.py`, add a new phase function:

```python
def _phase_signals(indexed_files: list[SourceFile], graph: GraphStore) -> None:
    """Phase N: Detect Django signal receivers."""
    logger.info("Detecting signals...")
    count = 0
    for source_file in indexed_files:
        result = detect_signals(source_file, graph)
        for rel in result.relationships:
            if graph.get_symbol(rel.source_id) and graph.get_symbol(rel.target_id):
                graph.add_relationship(rel)
        count += len(result.relationships)
    logger.info("Detected %d signal connections", count)
```

Wire it into `_full_analyze()` after the relevant phase.

### 4. Reference implementations

| Pattern | File to study |
|---------|--------------|
| Simple AST extraction | `src/pyxus/core/symbol_extractor.py` |
| Inheritance from AST | `src/pyxus/core/heritage.py` |
| Namespace-aware visitors | `src/pyxus/core/call_resolver.py` |
| Import resolution | `src/pyxus/core/import_resolver.py` |
| AST helper utilities | `src/pyxus/core/ast_utils.py` |
