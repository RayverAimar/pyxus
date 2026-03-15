# Rule 5: Consistency — Follow Existing Patterns

When a codebase establishes a pattern, all new code must follow it. This is especially critical for Pyxus because AI agents generating code tend to create new patterns rather than discovering and following existing ones.

**Before flagging any consistency issue, you MUST search the codebase.** Don't assume what the patterns are — look at the actual code. For every new class, function, or module, find the 2-3 most similar existing implementations and compare.

## AST Visitor pattern

All AST visitors in Pyxus follow this structure:

```python
# 1. Private class with underscore prefix
class _SymbolVisitor(ast.NodeVisitor):
    """Walks a Python AST and collects [what it collects]."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.symbols: list[Symbol] = []        # Public results
        self._class_stack: list[str] = []      # Private tracking state

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Extract a CLASS symbol and visit its body for methods."""
        # ... process node ...
        self._class_stack.append(symbol_id)
        self.generic_visit(node)               # Always call generic_visit for body
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract a function or method symbol."""
        # ... process node ...

    visit_AsyncFunctionDef = visit_FunctionDef  # Handle async identically
```

**Key rules:**
1. Private class (`_ClassName`)
2. `__init__` takes `file_path: str` and initializes results + tracking state
3. `visit_*` methods process the node and call `self.generic_visit(node)` for children
4. `visit_AsyncFunctionDef = visit_FunctionDef` — async handled identically
5. For class body traversal, use stack push/pop around `self.generic_visit(node)`

**Reference:** `symbol_extractor.py:_SymbolVisitor`, `call_resolver.py:_NamespaceTrackingVisitor` (base), `_AssignmentCollector`, `_AssignmentPropagator`

### Namespace tracking pattern

When visitors need to track the current scope:

```python
class _NamespaceTrackingVisitor(ast.NodeVisitor):
    """Base class that tracks the current namespace as it walks the AST."""

    def __init__(self, file_path: str) -> None:
        self._ns_stack: list[str] = [_module_ns(file_path)]
        self._class_stack: list[str] = []

    @property
    def _current_ns(self) -> str:
        return ".".join(self._ns_stack)
```

New visitors that need scope tracking should extend this base class (from `call_resolver.py`), not reinvent the pattern.

## Public API pattern

Every source module follows the pattern: one public function as the entry point, private helpers for implementation.

```python
# PUBLIC — the module's API
def extract_symbols(source_file: SourceFile) -> ExtractionResult:
    """Parse a Python file and extract all symbols."""
    ...

# PRIVATE — implementation details
def _classify_method(decorators: list[str]) -> SymbolKind:
    ...

class _SymbolVisitor(ast.NodeVisitor):
    ...
```

**How to check:** Look at existing modules in the same directory. Each has exactly one (or a few) public functions, and everything else is private.

| Module | Public API |
|--------|-----------|
| `symbol_extractor.py` | `extract_symbols()` |
| `heritage.py` | `extract_heritage()`, `ClassHierarchy` class |
| `import_resolver.py` | `build_file_index()`, `resolve_imports()` |
| `call_resolver.py` | `resolve_calls()`, `AssignmentGraph` class |
| `analyzer.py` | `analyze()` |
| `file_walker.py` | `walk_repository()`, `get_modified_files()`, `SourceFile` |
| `store.py` | `GraphStore` class |
| `queries.py` | `context()`, `impact()`, `query()` |
| `persistence.py` | `save_graph()`, `load_graph()`, `get_index_metadata()`, `export_json()` |

## Pipeline integration pattern

New analysis modules integrate into the pipeline via `analyzer.py`:

```python
# analyzer.py adds a new phase function:
def _phase_new_feature(indexed_files: list[SourceFile], graph: GraphStore, stats: AnalysisStats) -> None:
    """Phase N: Description of what this phase does."""
    logger.info("Running new feature analysis...")
    # ... process files, add to graph ...
    logger.info("New feature: %d items found", count)
```

**Key:** Phase functions are private (`_phase_*`), take the graph and stats as parameters, log progress with `logger.info()`.

## CLI command pattern

```python
@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--flag", is_flag=True, help="Description.")
def command_name(path: str, flag: bool) -> None:
    """Short description for --help output."""
    # Deferred import to avoid loading modules on CLI startup
    from pyxus.some.module import function
    ...
```

**Key:** Deferred imports inside command functions for fast CLI startup.

## MCP tool pattern

```python
@mcp.tool()
def tool_name(param: str) -> str:
    """Docstring becomes the tool description for AI agents.

    Args:
        param: Description for the AI agent.
    """
    graph = _get_graph()
    if graph is None:
        return _no_index_error()
    result = _query_function(graph, param)
    return json.dumps(result, indent=2)
```

**Key:** Always check for `None` graph, always return JSON string.

## Search strategy

For each new piece of code in the diff:

1. **Identify the pattern category** — Is this a new AST visitor? A new graph operation? A new CLI command? A new test file?
2. **Find 2-3 existing examples** of that category in the codebase (use Grep/Glob)
3. **Compare structure, naming, and approach** — Do they match?
4. **If they don't match, flag it** — Explain what the existing pattern is and reference the specific file

```bash
# Search examples:
# Find all AST visitors
grep -r "class _.*Visitor" src/pyxus/

# Find all public API functions in core/
grep -r "^def [a-z]" src/pyxus/core/

# Find all _phase_ functions
grep -r "def _phase_" src/pyxus/

# Find all _make_ test helpers
grep -r "def _make_" tests/
```
