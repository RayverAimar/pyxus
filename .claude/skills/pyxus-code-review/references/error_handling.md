# Rule 3: Error Handling Patterns

Pyxus processes arbitrary Python code — including code with syntax errors, encoding issues, and missing files. The error handling strategy is: **never crash, never propagate exceptions to callers, always produce usable output**.

## Pattern 1: AST parsing errors — return empty result

When parsing source code fails, log a warning and return an empty result object. **Never return None.** Callers should not need null checks after calling extraction/resolution functions.

```python
# CORRECT — empty result on SyntaxError
def extract_symbols(source_file: SourceFile) -> ExtractionResult:
    try:
        tree = ast.parse(source_file.content, filename=source_file.path)
    except SyntaxError as e:
        logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
        return ExtractionResult(symbols=[], relationships=[])
    # ... continue with valid tree

# BAD — returns None, forces callers to handle
def extract_symbols(source_file: SourceFile) -> ExtractionResult | None:
    try:
        tree = ast.parse(source_file.content, filename=source_file.path)
    except SyntaxError:
        return None  # Every caller now needs `if result is not None:`
```

This pattern applies to ALL functions that parse AST:
- `extract_symbols()` in `symbol_extractor.py`
- `extract_heritage()` in `heritage.py`
- `resolve_imports()` in `import_resolver.py`
- `resolve_calls()` (skips files with SyntaxError, continues with others) in `call_resolver.py`

**Reference:** `symbol_extractor.py:48-52`, `heritage.py:43-47`, `import_resolver.py:107-111`

### Logger format for SyntaxError

Always use this exact format (consistent across all modules):

```python
logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
```

## Pattern 2: File I/O errors — skip and continue

When reading files, catch encoding and OS errors individually. Log a warning and skip the file.

```python
# CORRECT — from file_walker.py
try:
    content = abs_path.read_text(encoding="utf-8")
except UnicodeDecodeError:
    try:
        content = abs_path.read_text(encoding="latin-1")
        logger.warning("Non-UTF8 file read with latin-1 fallback: %s", rel_path)
    except (UnicodeDecodeError, OSError):
        logger.warning("Skipping unreadable file: %s", rel_path)
        continue
except OSError as e:
    logger.warning("Skipping file due to OS error: %s (%s)", rel_path, e)
    continue
```

**Key:** Always use `logger.warning()` for file errors, never `logger.error()`. File errors during analysis are expected (unreadable files, permission issues) and shouldn't alarm users.

## Pattern 3: "Not found" lookups — return None

This is different from error handling. When looking up something that may not exist, returning None is correct:

```python
# CORRECT — "not found" returns None
def get_symbol(self, symbol_id: str) -> Symbol | None:
    idx = self._id_to_index.get(symbol_id)
    if idx is None:
        return None
    return self._graph[idx]

# CORRECT — load from disk, may not exist
def load_graph(repo_path: str) -> GraphStore | None:
    graph_path = Path(repo_path) / PYXUS_DIR / GRAPH_FILE
    if not graph_path.exists():
        return None
    ...
```

The distinction: **errors during processing** return empty results (never None); **lookups for optional data** return None.

## Pattern 4: Corrupted persistence — return None with helpful message

```python
# CORRECT — from persistence.py
try:
    with graph_path.open("rb") as f:
        state = pickle.load(f)  # noqa: S301
    return GraphStore.from_state(state)
except (pickle.UnpicklingError, EOFError, AttributeError, KeyError) as e:
    logger.warning("Corrupted index at %s: %s. Run `pyxus analyze` to rebuild.", graph_path, e)
    return None
```

**Key:** Include actionable recovery instruction in the warning message.

## Pattern 5: subprocess errors — return None or empty

```python
# CORRECT — from file_walker.py
try:
    result = subprocess.run(
        ["git", "ls-files", ...],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    ...
except (FileNotFoundError, subprocess.TimeoutExpired):
    return None
```

**Key:** Always set `timeout` on subprocess calls. Catch `FileNotFoundError` (git not installed) and `TimeoutExpired`.

## Pattern 6: MCP server errors — return helpful JSON

```python
# CORRECT — from server.py
def _no_index_error() -> str:
    return json.dumps({
        "error": "No Pyxus index found. Run `pyxus analyze` first to index your codebase.",
    })

@mcp.tool()
def context(name: str) -> str:
    graph = _get_graph()
    if graph is None:
        return _no_index_error()
    ...
```

## What to check in reviews

1. **New AST parsing** — Does it catch `SyntaxError` and return an empty result (not None)?
2. **Logger format** — Is the SyntaxError warning format consistent with other modules?
3. **File operations** — Are `UnicodeDecodeError`, `OSError` caught? Is there a `timeout` on subprocess?
4. **Return types** — Does the function return None only for "not found" cases, not for errors?
5. **Warning messages** — Do they include the file path and actionable recovery instructions?
6. **Exception specificity** — Are exceptions caught specifically (not bare `except:` or `except Exception:`)?
