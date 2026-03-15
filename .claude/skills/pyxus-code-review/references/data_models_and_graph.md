# Rule 2: Data Models and Graph API

Pyxus's graph is built on frozen dataclasses and a rustworkx wrapper. Getting these patterns wrong means corrupted graph data, broken queries, or subtle bugs that only surface when analyzing real projects.

## Frozen dataclasses for graph data

**Symbols and Relationships MUST be frozen.** They are graph nodes and edges — mutating them after insertion would silently invalidate indexes.

```python
# CORRECT — frozen, hashable, immutable
@dataclass(frozen=True)
class Symbol:
    id: str
    name: str
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    decorators: tuple[str, ...] = ()          # tuple, NOT list (hashable)
    is_exported: bool = True
    metadata: dict = field(default_factory=dict, hash=False, compare=False)

# BAD — mutable, not hashable
@dataclass
class Symbol:              # Missing frozen=True
    decorators: list[str]  # list instead of tuple — not hashable
    metadata: dict         # Missing hash=False, compare=False
```

### Key rules for frozen dataclasses

1. **Collections must be tuples** (not lists) — for hashability: `decorators: tuple[str, ...] = ()`
2. **Mutable fields (dict) must exclude from hash/compare** — `field(default_factory=dict, hash=False, compare=False)`
3. **All fields must have type hints**
4. **Defaults use field()** for mutable types, direct values for immutable types

## Result containers are NOT frozen

Result dataclasses (pipeline outputs) are regular mutable dataclasses. They're consumed and discarded, not stored in the graph.

```python
# CORRECT — mutable result container
@dataclass
class ExtractionResult:
    """The output of extracting symbols from a single source file."""
    symbols: list[Symbol]
    relationships: list[Relationship]

@dataclass
class AnalysisStats:
    """Summary statistics for a completed analysis run."""
    files_found: int = 0
    files_indexed: int = 0
    call_resolution_rate: float = 0.0
```

**Reference:** `graph/models.py` for frozen models, `core/symbol_extractor.py` for result containers.

## Symbol ID format

Symbol IDs are deterministic and follow this exact format:

```
{kind}:{file_path}:{name}:{line}
```

Examples:
```
class:services/profiles.py:ProfileService:42
method:services/profiles.py:create:45
module:utils.py:utils.py:0
function:utils.py:helper:10
```

**Always use `make_symbol_id()`** — never construct IDs manually:

```python
# BAD — manual ID construction
symbol_id = f"class:{file_path}:{name}:{line}"

# GOOD — factory function
from pyxus.graph.models import make_symbol_id
symbol_id = make_symbol_id(SymbolKind.CLASS, file_path, name, line)
```

## Relationship ID format

```
{kind}:{source_id}->{target_id}
```

**Always use `make_relationship_id()`**:

```python
# BAD
rel_id = f"calls:{caller_id}->{callee_id}"

# GOOD
from pyxus.graph.models import make_relationship_id
rel_id = make_relationship_id(caller_id, callee_id, RelationKind.CALLS)
```

## GraphStore API usage

### Adding symbols (idempotent)

```python
# GraphStore.add_symbol() is idempotent — safe to call twice
idx = graph.add_symbol(symbol)  # Returns node index
idx2 = graph.add_symbol(symbol)  # Same index, no duplicate
```

### Adding relationships (requires both endpoints)

```python
# GOOD — both symbols exist
graph.add_symbol(source_sym)
graph.add_symbol(target_sym)
graph.add_relationship(rel)

# BAD — will raise KeyError if either endpoint doesn't exist
graph.add_relationship(rel)  # KeyError: "Source symbol not found: ..."
```

**Safety pattern in pipeline code** (see `analyzer.py`):

```python
# Defensive check before adding edges from external resolution
for rel in import_result.relationships:
    if graph.get_symbol(rel.source_id) and graph.get_symbol(rel.target_id):
        graph.add_relationship(rel)
```

### Querying the graph

```python
# By name — returns list (may be empty, may have multiple)
symbols = graph.get_symbol_by_name("ProfileService")

# By ID — returns Symbol or None
symbol = graph.get_symbol("class:f.py:Foo:1")

# By file — all symbols in a file
symbols = graph.get_symbols_in_file("services/profiles.py")

# Traversal — predecessors/successors return (Symbol, Relationship) tuples
for sym, rel in graph.predecessors(symbol_id):
    ...

# Filtered traversal
callers = graph.predecessors_by_kind(symbol_id, RelationKind.CALLS)
methods = graph.successors_by_kind(class_id, RelationKind.HAS_METHOD)
```

## Enums

SymbolKind and RelationKind use `StrEnum` (not `Enum`). This means values are their string representations:

```python
class SymbolKind(StrEnum):
    MODULE = "module"
    CLASS = "class"
    METHOD = "method"
    FUNCTION = "function"
    PROPERTY = "property"
    CLASSMETHOD = "classmethod"
    STATICMETHOD = "staticmethod"

class RelationKind(StrEnum):
    DEFINES = "defines"
    HAS_METHOD = "has_method"
    CALLS = "calls"
    IMPORTS = "imports"
    EXTENDS = "extends"
```

**Only add new enum values when implementing the code that uses them.** Do not add Django/Celery/Intelligence kinds in advance.

```python
# BAD — adding enum values for future use
class RelationKind(StrEnum):
    CALLS = "calls"
    FK = "foreign_key"       # Not implemented yet!
    QUEUES_TASK = "queues_task"  # Not implemented yet!

# GOOD — only values that are actually used by current code
class RelationKind(StrEnum):
    CALLS = "calls"
    # FK, QUEUES_TASK etc. will be added when Django/Celery plugins are implemented
```

## What to check in reviews

1. **New dataclasses** — Are graph data models frozen? Are result containers mutable? Are collection fields tuples?
2. **ID construction** — Are `make_symbol_id()` and `make_relationship_id()` used instead of f-strings?
3. **Graph operations** — Are relationships added after both endpoints exist? Is the defensive check pattern used?
4. **Enum values** — Are new enum values only added when the code that uses them exists?
5. **Type hints** — Are all dataclass fields typed? Are Optional fields using `| None` syntax?
