# How to: Write Tests for New Code

Every new source file needs a matching test file. This guide shows how to write tests that follow the established patterns.

## Test file template

For a new source file `src/pyxus/plugins/django/signals.py`, create `tests/plugins/django/test_signals.py`:

```python
"""Tests for plugins/django/signals.py."""

from pyxus.core.file_walker import SourceFile
from pyxus.graph.models import RelationKind, SymbolKind
from pyxus.graph.store import GraphStore
from pyxus.plugins.django.signals import detect_signals


def _make_signal_detection(code: str, path: str = "test.py"):
    """Detect signals in a code string with a pre-populated graph."""
    sf = SourceFile(path=path, absolute_path=f"/tmp/{path}", content=code)
    graph = GraphStore()
    # Pre-populate graph with symbols that signals reference
    # ... add necessary symbols ...
    return detect_signals(sf, graph)


class TestReceiverDecorator:
    def test_detects_post_save_receiver(self):
        code = '''
from django.dispatch import receiver
from django.db.models.signals import post_save

@receiver(post_save, sender=Profile)
def on_profile_save(sender, instance, **kwargs):
    pass
'''
        result = _make_signal_detection(code)
        assert len(result.relationships) == 1
        rel = result.relationships[0]
        assert rel.kind == RelationKind.RECEIVES_SIGNAL
        # Verify all relevant fields
        assert "on_profile_save" in rel.source_id
        assert "Profile" in rel.target_id

    def test_multiple_signals_in_one_decorator(self):
        ...


class TestSignalConnect:
    def test_detects_connect_call(self):
        ...


class TestEdgeCases:
    def test_syntax_error_returns_empty(self):
        sf = SourceFile(path="bad.py", absolute_path="/tmp/bad.py", content="def broken(:\n")
        graph = GraphStore()
        result = detect_signals(sf, graph)
        assert result.relationships == []

    def test_empty_file(self):
        result = _make_signal_detection("")
        assert result.relationships == []

    def test_file_without_signals(self):
        result = _make_signal_detection("def helper():\n    pass\n")
        assert result.relationships == []
```

## Checklist for every new test file

1. **Module docstring**: `"""Tests for path/to/module.py."""`
2. **NO `from __future__ import annotations`** in test files
3. **`_make_*` builders** for test data — docstring if non-obvious
4. **Class-based grouping** — `class TestFeatureName:`
5. **Edge case class** — `class TestEdgeCases:` with SyntaxError, empty file, no matches
6. **All fields verified** — not just one assertion per test
7. **Descriptive test names** — `test_detects_post_save_receiver`, not `test_basic`

## When to use pytest fixtures

Use fixtures ONLY for:

```python
# 1. Side effects that need cleanup (autouse)
@pytest.fixture(autouse=True)
def _reset_cache():
    import pyxus.server as srv
    srv._graph_cache = None
    yield
    srv._graph_cache = None

# 2. Complex shared setup used by 3+ test classes
@pytest.fixture
def populated_graph():
    """A graph with 6 symbols and 5 relationships."""
    g = GraphStore()
    # ... 30+ lines of setup ...
    return g
```

For everything else, use `_make_*` helpers.

## Integration test pattern

For features that need full pipeline testing, add to `tests/test_integration.py` or create a new integration test file with a fixture project:

```python
class TestDjangoPlugin:
    def test_fk_relationships_detected(self, django_project_graph):
        """FK edges should connect models."""
        rels = [r for r in django_project_graph.relationships()
                if r.kind == RelationKind.FK]
        assert len(rels) >= 1

    def test_signal_wiring_detected(self, django_project_graph):
        ...
```

Fixture projects go in `tests/fixtures/<project_name>/` with minimal but realistic Python code.

## Reference test files

| Type of test | Reference file |
|-------------|---------------|
| Simple unit tests | `tests/core/test_symbol_extractor.py` |
| Multi-file resolution | `tests/core/test_call_resolver.py` |
| Complex fixture setup | `tests/graph/test_queries.py` |
| Data model tests | `tests/graph/test_models.py` |
| CLI tests | `tests/test_cli.py` |
| Server/MCP tests | `tests/test_server.py` |
| End-to-end integration | `tests/test_integration.py` |
