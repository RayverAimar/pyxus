# How to: Integrate New Code into the Pipeline

This guide covers adding new analysis phases to `analyzer.py` and new CLI/MCP commands.

## Adding a new pipeline phase

### 1. Create the phase function in `analyzer.py`

```python
def _phase_plugins(
    indexed_files: list[SourceFile],
    graph: GraphStore,
    stats: AnalysisStats,
) -> None:
    """Phase N: Run framework-specific plugin analyzers."""
    logger.info("Running plugins...")
    # ... plugin detection and analysis ...
    logger.info("Plugins: %d framework relationships added", count)
```

**Pattern from existing phases:**
- Private function: `_phase_*`
- Parameters: `indexed_files`, `graph`, `stats` (always these three, plus extras if needed)
- Logging: `logger.info()` at start and end with counts
- Returns: void (modifies graph in place) or a result object (like `_phase_calls` returns `CallResolutionResult`)

### 2. Wire into `_full_analyze()`

```python
def _full_analyze(repo_path: str, stats: AnalysisStats, start_time: float) -> AnalysisResult:
    graph = GraphStore()

    files = _phase_walk(repo_path, stats)
    if not files:
        ...

    indexed_files = _phase_extract(files, graph, stats)
    class_hierarchy = _phase_heritage(indexed_files, graph)
    _phase_imports(indexed_files, graph, stats)
    call_result = _phase_calls(indexed_files, graph, class_hierarchy, stats)
    _phase_plugins(indexed_files, graph, stats)  # NEW — after core analysis
    ...
```

**Order matters:** Plugins run AFTER core analysis (symbols, heritage, imports, calls) because they depend on symbols already being in the graph.

### 3. Update AnalysisStats if needed

```python
@dataclass
class AnalysisStats:
    # ... existing fields ...
    plugin_relationships: int = 0  # Add new field with default
```

## Adding a new CLI command

```python
# In cli.py
@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--verbose", is_flag=True, help="Show detailed output.")
def new_command(path: str, verbose: bool) -> None:
    """Short description shown in --help."""
    # Deferred import — keep CLI startup fast
    from pyxus.some.module import function

    repo_path = str(Path(path).resolve())
    result = function(repo_path)
    click.echo(f"Result: {result}")
```

**Key patterns:**
- `@main.command()` — always under the `main` group
- `click.argument("path", default=".")` — path argument with current dir default
- Deferred imports inside the function body
- `click.echo()` for output (not `print()`)

## Adding a new MCP tool

```python
# In server.py
@mcp.tool()
def new_tool(param: str, option: int = 5) -> str:
    """Docstring becomes the AI agent's tool description.

    Args:
        param: What this parameter is for.
        option: What this option controls (default 5).
    """
    graph = _get_graph()
    if graph is None:
        return _no_index_error()
    result = _query_function(graph, param, option)
    return json.dumps(result, indent=2)
```

**Key patterns:**
- `@mcp.tool()` decorator
- Docstring with Args section (AI agents read this)
- Always check `_get_graph()` for None
- Return `json.dumps(result, indent=2)` — always JSON string

## Adding a new MCP resource

```python
@mcp.resource("pyxus://resource_name")
def resource_name() -> str:
    """Description of what this resource provides."""
    repo_path = os.environ.get("PYXUS_REPO_PATH") or _find_repo_root()
    # ... compute result ...
    return json.dumps(data, indent=2)
```

## Reference files

| What | File |
|------|------|
| Pipeline orchestration | `src/pyxus/core/analyzer.py` |
| CLI commands | `src/pyxus/cli.py` |
| MCP server | `src/pyxus/server.py` |
| CLI tests | `tests/test_cli.py` |
| Server tests | `tests/test_server.py` |
