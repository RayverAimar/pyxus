# Rule 6: Python Best Practices (Non-Obvious)

Beyond PEP 8 and basic formatting (which ruff handles), there are Python best practices that only a careful review catches. These are the patterns that separate professional Python from "code that works."

## `__all__` exports on public modules

Modules that expose a public API should define `__all__` to make the API explicit. This affects `from module import *`, IDE autocomplete, and documentation tools.

```python
# src/pyxus/graph/models.py
__all__ = ["Symbol", "Relationship", "SymbolKind", "RelationKind", "make_symbol_id", "make_relationship_id"]
```

**When to require:** Package `__init__.py` files that re-export names, and modules with a mix of public and private names.

**When to skip:** Modules where everything is private except one obvious function (e.g., `symbol_extractor.py` with just `extract_symbols()`).

## `@functools.cache` for expensive pure computations

If a method takes immutable arguments and does expensive work, cache it.

```python
# BAD — recomputes C3 linearization every time
def get_mro(self, class_id: str) -> list[str]:
    return self._c3_linearize(class_id)

# GOOD — cached result for repeat calls
import functools

@functools.cache
def get_mro(self, class_id: str) -> list[str]:
    return self._c3_linearize(class_id)
```

**Candidates in Pyxus:**
- `ClassHierarchy.get_mro()` — called repeatedly during call resolution
- `ClassHierarchy.resolve_attribute()` — called for every `obj.method()` resolution

**When NOT to cache:**
- Methods that read mutable state (caching would return stale data)
- Methods with mutable arguments (unhashable, can't be cached)
- One-shot functions called once per pipeline run

## `list.extend()` over repeated `list.append()` in loops

`extend()` avoids repeated method lookups and allows batch allocation.

```python
# BAD — method lookup on every iteration
for item in items:
    result.append(transform(item))

# GOOD — single method call
result.extend(transform(item) for item in items)
```

Ruff rule `PERF401` catches this automatically, but review for cases where the transformation is complex enough that a loop is clearer.

## Subprocess safety

Always use list form (not string) for subprocess commands. Always set `timeout`. Mark intentional security decisions with specific `noqa` comments:

```python
# GOOD — list form, timeout, specific noqa
result = subprocess.run(
    ["git", "ls-files", "*.py"],  # noqa: S607
    capture_output=True,
    text=True,
    timeout=30,
)

# BAD — string form (shell injection risk), no timeout
result = subprocess.run("git ls-files *.py", shell=True)
```

**S607** (partial executable path): Always suppress for `git` — it's expected to be on PATH.
**S603** (untrusted input): Only suppress when the input is from trusted sources (our own metadata). Flag if user-supplied data goes into subprocess args.

## Ruff rules we enforce

The project uses expanded ruff rules beyond the basics:

```toml
select = ["E", "F", "I", "UP", "B", "SIM", "RUF", "PERF", "PIE", "LOG", "C4", "S"]
```

| Rule set | What it catches |
|----------|----------------|
| `E`, `F` | PEP 8, pyflakes basics |
| `I` | Import ordering |
| `UP` | Python version upgrades (use 3.12+ syntax) |
| `B` | Bugbear (common mistakes) |
| `SIM` | Simplifiable code |
| `RUF` | Ruff-specific: unused noqa, mutable class defaults, etc. |
| `PERF` | Performance: `extend` vs `append`, unnecessary `dict()` calls |
| `PIE` | Misc improvements |
| `LOG` | Logging best practices |
| `C4` | Comprehension simplification |
| `S` | Bandit security (with per-file ignores for tests) |

**Per-file ignores:**
```toml
"tests/**" = ["S101", "S108"]  # assert and /tmp paths are expected in tests
```

## `StrEnum` over `Enum` for string-valued enums

Python 3.11+ `StrEnum` eliminates the need for `.value` in comparisons and JSON serialization:

```python
# GOOD — StrEnum (values are strings)
class SymbolKind(StrEnum):
    CLASS = "class"
    METHOD = "method"

# Usage: symbol.kind == "class" works
# JSON: json.dumps({"kind": symbol.kind}) works without .value

# BAD — plain Enum requires .value everywhere
class SymbolKind(Enum):
    CLASS = "class"
    METHOD = "method"

# Usage: symbol.kind.value == "class" (verbose)
```

## Frozen dataclasses: `tuple` not `list`, `field(hash=False)`

```python
# GOOD — hashable frozen dataclass
@dataclass(frozen=True)
class Symbol:
    decorators: tuple[str, ...] = ()                    # tuple, not list
    metadata: dict = field(default_factory=dict,
                          hash=False, compare=False)    # excluded from hash

# BAD — unhashable
@dataclass(frozen=True)
class Symbol:
    decorators: list[str] = field(default_factory=list)  # TypeError on hash()
    metadata: dict = field(default_factory=dict)          # included in hash (wrong)
```

## `defaultdict` for accumulation patterns

```python
# GOOD — no KeyError checks
from collections import defaultdict
_name_to_ids: defaultdict[str, list[str]] = defaultdict(list)
_name_to_ids[name].append(symbol_id)  # just works

# BAD — manual key checking
_name_to_ids: dict[str, list[str]] = {}
if name not in _name_to_ids:
    _name_to_ids[name] = []
_name_to_ids[name].append(symbol_id)
```

## `PurePosixPath` for cross-platform path manipulation

When manipulating file paths as strings (not filesystem operations), use `PurePosixPath` for consistent behavior across platforms:

```python
from pathlib import PurePosixPath

# GOOD — works on Windows and Unix
path = PurePosixPath(file_path)
parts = list(path.parts)

# BAD — breaks on Windows
parts = file_path.split("/")
```

## `logging` lazy formatting

Use `%s` formatting in logger calls, not f-strings or `.format()`. The formatting is only evaluated if the log level is enabled:

```python
# GOOD — lazy (formatting skipped if level is below WARNING)
logger.warning("Syntax error in %s (line %s): %s", path, lineno, msg)

# BAD — always evaluates the f-string even if not logged
logger.warning(f"Syntax error in {path} (line {lineno}): {msg}")
```

Ruff rule `LOG` catches this automatically.

## What to check in reviews

1. **New modules** — Should they define `__all__`?
2. **Expensive computations** — Can they be cached with `@functools.cache`?
3. **Loops with append** — Can they use `extend()` instead?
4. **Subprocess calls** — List form? `timeout` set? Proper `noqa` if needed?
5. **New enums** — Using `StrEnum`, not `Enum`?
6. **New dataclasses** — Frozen for graph data? `tuple` for sequences? `hash=False` for metadata?
7. **Logging** — Using `%s` formatting, not f-strings?
8. **Path manipulation** — Using `PurePosixPath` for string paths?
