# How to: Extend the Graph Data Model

This guide covers adding new SymbolKind values, RelationKind values, or modifying data models.

## Adding a new RelationKind

When implementing a new feature (e.g., Django FK detection), you need new relationship types.

### 1. Add enum value to `graph/models.py`

```python
class RelationKind(StrEnum):
    # Core Python (existing)
    DEFINES = "defines"
    HAS_METHOD = "has_method"
    CALLS = "calls"
    IMPORTS = "imports"
    EXTENDS = "extends"
    # Django (add when implementing Django plugin)
    FK = "foreign_key"
    O2O = "one_to_one"
    M2M = "many_to_many"
```

**Rule:** Only add enum values when you're implementing the code that creates them. Never add values speculatively.

### 2. Create relationships using factory functions

```python
from pyxus.graph.models import RelationKind, Relationship, make_relationship_id

rel = Relationship(
    id=make_relationship_id(source_sym.id, target_sym.id, RelationKind.FK),
    source_id=source_sym.id,
    target_id=target_sym.id,
    kind=RelationKind.FK,
    confidence=1.0,  # Direct observation = 1.0; inferred = lower
    metadata={"field_name": "organization"},  # Optional context
)
```

### 3. Add to graph with defensive checks

```python
# Always verify both endpoints exist before adding
if graph.get_symbol(rel.source_id) and graph.get_symbol(rel.target_id):
    graph.add_relationship(rel)
```

### 4. Update queries if needed

If the new relationship type should appear in `context()` output, check `graph/queries.py`:
- `_group_edges()` already groups by `rel.kind.value`, so new kinds appear automatically
- If special handling is needed (e.g., showing FK targets in a special section), add it to `context()`

### 5. Update tests

Add to `tests/graph/test_models.py`:
```python
class TestRelationKind:
    def test_has_all_core_values(self):
        assert RelationKind.FK == "foreign_key"
        # ... test all new values
```

## Adding a new SymbolKind (rare)

New SymbolKind values are uncommon. The existing set covers all standard Python constructs. Only add for framework-specific concepts that don't map to existing kinds.

## Modifying Symbol or Relationship

**Do NOT add new required fields.** This would break all existing tests and possibly the persistence layer.

For new optional data, use the `metadata` dict:

```python
# GOOD — extend via metadata (no schema change)
symbol = Symbol(
    id=make_symbol_id(SymbolKind.CLASS, path, name, line),
    name="Profile",
    kind=SymbolKind.CLASS,
    file_path=path,
    start_line=line,
    end_line=end_line,
    metadata={"django_model": True, "abstract": False},  # Framework-specific data
)

# BAD — adding new fields to the frozen dataclass
@dataclass(frozen=True)
class Symbol:
    ...
    is_django_model: bool = False  # Don't do this
```

## Reference files

| What | File |
|------|------|
| Data model definitions | `src/pyxus/graph/models.py` |
| Graph wrapper API | `src/pyxus/graph/store.py` |
| Query API | `src/pyxus/graph/queries.py` |
| Model tests | `tests/graph/test_models.py` |
| Store tests | `tests/graph/test_store.py` |
