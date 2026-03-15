# Rule 4: Test Patterns

Every source file needs a matching test file. Tests are the safety net for a static analysis tool — if the tests are weak, wrong analysis results ship silently.

## Test file structure

```python
"""Tests for core/symbol_extractor.py."""            # 1. Module docstring (path to source)

from pyxus.core.file_walker import SourceFile        # 2. Imports (no __future__)
from pyxus.core.symbol_extractor import extract_symbols
from pyxus.graph.models import RelationKind, SymbolKind


def _make_extraction(code: str, path: str = "test.py"):  # 3. Local _make_ helpers
    """Extract symbols from a code string for testing."""
    sf = SourceFile(path=path, absolute_path=f"/tmp/{path}", content=code)
    return extract_symbols(sf)


class TestClassExtraction:                           # 4. Class-based grouping
    def test_extracts_class(self):
        result = _make_extraction("class Foo:\n    pass\n")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert cls.name == "Foo"
        assert cls.file_path == "test.py"
        assert cls.start_line == 1
        assert cls.end_line == 2
        assert cls.is_exported is True
        assert cls.decorators == ()                  # 5. Verify ALL fields
```

**Reference files:**
- Simple tests: `tests/core/test_symbol_extractor.py`
- Complex builders: `tests/core/test_call_resolver.py`
- Fixture usage: `tests/graph/test_queries.py`
- Integration: `tests/test_integration.py`

## Test file naming

- Source: `src/pyxus/core/symbol_extractor.py` → Test: `tests/core/test_symbol_extractor.py`
- Source: `src/pyxus/graph/store.py` → Test: `tests/graph/test_store.py`
- Source: `src/pyxus/server.py` → Test: `tests/test_server.py`

**Every new source file needs a matching test file.** No exceptions.

## _make_ helpers vs @pytest.fixture

### Use `_make_*` helpers for:
- Simple data construction without side effects
- Per-test setup that varies between tests
- Trivial builders (one-liners)

```python
# GOOD — _make_ builder for simple construction
def _make_store() -> GraphStore:
    return GraphStore()

def _make_class_symbol() -> Symbol:
    return Symbol(
        id="class:f.py:Foo:1",
        name="Foo",
        kind=SymbolKind.CLASS,
        file_path="f.py",
        start_line=1,
        end_line=20,
    )
```

### Use `@pytest.fixture` for:
- **Setup/teardown with side effects** (cache reset, global state cleanup)
- **Complex shared setup** used across multiple test classes in the same file

```python
# GOOD — fixture for side effects (autouse to reset cache)
@pytest.fixture(autouse=True)
def _reset_server_cache():
    """Reset the module-level graph cache between tests."""
    import pyxus.server as srv
    srv._graph_cache = None
    srv._repo_path = None

# GOOD — fixture for complex setup shared across 5+ test classes
@pytest.fixture
def graph_with_service():
    """A graph representing a simple Service class with methods and callers."""
    g = GraphStore()
    # ... 30 lines of setup ...
    return g

class TestContext:
    def test_returns_class_with_methods(self, graph_with_service):
        result = context(graph_with_service, "Service")
        ...

class TestImpact:
    def test_upstream_impact(self, graph_with_service):
        result = impact(graph_with_service, "helper")
        ...
```

### BAD — fixture for simple construction

```python
# BAD — this should be a _make_ helper, not a fixture
@pytest.fixture
def store():
    return GraphStore()

@pytest.fixture
def class_symbol():
    return Symbol(id="class:f.py:Foo:1", ...)
```

## _make_ helper docstrings

- **Helpers with non-obvious behavior** (multiple params, complex setup) → docstring required
- **Trivial one-liner builders** → docstring optional

```python
# Docstring required — non-obvious what this does
def _make_call_resolution(codes: dict[str, str]) -> CallResolutionResult:
    """Resolve calls from multiple source code strings for testing."""
    ...

# Docstring optional — self-explanatory
def _make_store() -> GraphStore:
    return GraphStore()
```

## Class-based test grouping

**ALL tests use class-based grouping.** No standalone test functions.

```python
# BAD — standalone functions
def test_add_symbol():
    store = _make_store()
    ...

def test_get_symbol():
    store = _make_store()
    ...

# GOOD — grouped by feature
class TestAddAndGetSymbol:
    def test_add_and_get(self):
        store = _make_store()
        ...

    def test_get_nonexistent_returns_none(self):
        store = _make_store()
        ...
```

### Class naming

```python
# GOOD — descriptive class names
class TestClassExtraction:        # What it tests
class TestDirectFunctionCall:     # Specific scenario
class TestEdgeCases:              # Edge case group
class TestRiskThresholds:         # Specific behavior

# BAD — vague names
class Tests:
class TestMisc:
class TestStuff:
```

## Assertion patterns

### Verify ALL relevant fields

```python
# BAD — only checks one field
def test_extracts_class(self):
    result = _make_extraction("class Foo:\n    pass\n")
    cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
    assert cls.name == "Foo"  # What about file_path? start_line? is_exported?

# GOOD — verifies all relevant fields
def test_extracts_class(self):
    result = _make_extraction("class Foo:\n    pass\n")
    cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
    assert cls.name == "Foo"
    assert cls.file_path == "test.py"
    assert cls.start_line == 1
    assert cls.end_line == 2
    assert cls.is_exported is True
    assert cls.decorators == ()
```

### Assertion style

```python
# Exact equality for scalar values
assert cls.name == "Foo"
assert result.stats.total_calls >= 2

# Membership for collections
assert "dataclass" in cls.decorators
assert cls in f_symbols

# Set comparison for unordered collections
assert {c.name for c in classes} == {"Outer", "Inner"}

# Exception testing
with pytest.raises(KeyError, match="Source symbol not found"):
    store.add_relationship(rel)
```

## Edge case tests

Every module should have an edge case test class:

```python
class TestEdgeCases:
    def test_syntax_error_returns_empty(self):
        """SyntaxError must return empty result, not crash."""
        sf = SourceFile(path="bad.py", absolute_path="/tmp/bad.py", content="def broken(:\n")
        result = extract_symbols(sf)
        assert result.symbols == []
        assert result.relationships == []

    def test_empty_file(self):
        """Empty files should produce only a MODULE symbol."""
        result = _make_extraction("")
        assert len(result.symbols) == 1
        assert result.symbols[0].kind == SymbolKind.MODULE
```

## Shared helpers (tests/helpers.py)

Helpers used across multiple test files live in `tests/helpers.py` with **public names** (no underscore):

```python
# tests/helpers.py
def make_source_file(path: str = "test.py", content: str = "") -> SourceFile:
    """Create a SourceFile for testing without touching the filesystem."""
    return SourceFile(path=path, absolute_path=f"/tmp/{path}", content=content)

def make_project(tmp_path: Path, files: dict[str, str]) -> str:
    """Create a temporary Python project directory with the given files."""
    ...
```

**Key:** `tests/helpers.py` uses `from __future__ import annotations`. Regular test files do NOT.

## Integration tests

Integration tests in `tests/test_integration.py` use fixture projects from `tests/fixtures/`:

```python
class TestSimpleProject:
    def test_all_symbols_extracted(self, simple_project_graph):
        """Verify the full pipeline produces expected symbols."""
        ...

class TestComplexProject:
    def test_deep_inheritance(self, complex_project_graph):
        """Verify 3-level inheritance chain is detected."""
        ...
```

New fixture projects go in `tests/fixtures/<project_name>/` with realistic but minimal Python code.

## What to check in reviews

1. **Every new source file** has a matching test file
2. **Tests use class-based grouping** (no standalone functions)
3. **_make_ helpers** are used for data construction, not fixtures (unless shared across classes)
4. **All relevant fields** are verified in assertions, not just one
5. **Edge cases** are tested: SyntaxError, empty input, missing data
6. **Test class names** are descriptive and specific
7. **New _make_ helpers** with non-obvious behavior have docstrings
