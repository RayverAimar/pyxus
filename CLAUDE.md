# Pyxus — Python Code Intelligence Engine

## What is Pyxus

Static analysis tool for Python codebases that builds a knowledge graph of symbols, relationships, and execution flows. Exposes the graph via MCP for AI agents (Claude Code, Codex, Cursor).

Key differentiator: PyCG-inspired assignment graph resolves ~70% of calls **without type hints** via inter-procedural analysis.

## Stack

- **Language**: Python 3.12+ (3.13 pinned)
- **AST parsing**: stdlib `ast` module
- **Scope resolution**: stdlib `symtable` module
- **Graph storage**: `rustworkx.PyDiGraph` (in-memory, pickle persistence)
- **MCP server**: FastMCP standalone (v3.0+)
- **CLI**: `click`
- **Community detection**: `leidenalg` + `igraph`
- **Package manager**: `uv`
- **Linting/formatting**: `ruff` (line-length 120, py312 target)
- **Testing**: `pytest`

## Project layout

```
src/pyxus/
├── cli.py                  # CLI: analyze, status, clean, serve
├── server.py               # MCP server (FastMCP)
├── core/                   # Core Python analyzer (framework-agnostic)
│   ├── analyzer.py         # Pipeline orchestrator
│   ├── file_walker.py      # Repository file discovery
│   ├── symbol_extractor.py # AST → symbols
│   ├── import_resolver.py  # Import statements → file paths
│   ├── call_resolver.py    # Assignment graph engine (PyCG-inspired)
│   ├── heritage.py         # Class inheritance + MRO
│   └── scope.py            # symtable-based scope resolution
├── graph/                  # Knowledge graph
│   ├── models.py           # Node/Edge dataclasses (Symbol, Relationship)
│   ├── store.py            # rustworkx PyDiGraph wrapper
│   ├── queries.py          # context(), impact(), query()
│   └── persistence.py      # Save/load (pickle, JSON export)
├── intelligence/           # Higher-level analysis
│   ├── communities.py      # Leiden community detection
│   └── flows.py            # Execution flow tracing
└── plugins/                # Framework-specific analyzers
    ├── django/             # Django plugin (models, signals, urls, drf, admin, middleware)
    ├── celery/             # Celery plugin (tasks, .delay dispatch)
    └── fastapi/            # FastAPI plugin (future)
```

## Development commands

```bash
uv sync                       # Install dependencies
uv run pytest                 # Run tests
uv run ruff check .           # Lint
uv run ruff format .          # Format
uv run pyxus analyze <path>   # Analyze a Python project
uv run pyxus serve            # Start MCP server
```

## Implementation phases

Detailed plans are in the root: `PYXUS_PROJECT_PLAN.md`, `PYXUS_PHASE1_PLAN.md` through `PYXUS_PHASE4_PLAN.md`.

### Phase 1: Core Python Analyzer (COMPLETE)
All 14 tasks (1.1–1.15) are implemented with 184 passing tests.
Includes: graph models, rustworkx store, pickle persistence, file walker, AST symbol extraction, class hierarchy + MRO, scope resolution, import resolution, PyCG-style call resolution, pipeline orchestrator, context/impact/query queries, FastMCP server, click CLI, and integration tests with two fixture projects.

### Phase 2: Django Plugin
Plugin interface + Django model relationships, signals, URLs, DRF bindings, admin, middleware. Celery task detection.

### Phase 3: Intelligence Layer
Community detection (Leiden), execution flow tracing, text search, detect_changes (git diff → symbols).

### Phase 4: Polish & Ship
Incremental indexing, Claude Code hooks, performance testing, error handling, docs, PyPI publish.

## Key data model

- **Symbols**: MODULE, CLASS, METHOD, FUNCTION, PROPERTY, CLASSMETHOD, STATICMETHOD
- **Relationships**: DEFINES, HAS_METHOD, CALLS, IMPORTS, EXTENDS, FK, O2O, M2M, RECEIVES_SIGNAL, ROUTES_TO, SERIALIZES, FILTERS, ADMINISTERS, MIDDLEWARE_CHAIN, QUEUES_TASK, MEMBER_OF, STEP_IN_FLOW
- **Symbol ID format**: `{kind}:{file_path}:{name}:{line}`
- Symbols and Relationships are frozen dataclasses (hashable, immutable)

## Conventions

- Code is written in English; planning docs are in Spanish
- src layout (`src/pyxus/`)
- All public functions need type hints
- ruff lint rules: E, F, I, UP, B, SIM
- Double quote style
- Tests go in `tests/` mirroring `src/pyxus/` structure, with fixtures in `tests/fixtures/`
- Graph persistence: `.pyxus/graph.pkl` + `metadata.json` in the analyzed repo
- CI: GitHub Actions runs lint + format check + tests with 90% coverage threshold

## Code patterns

### Error handling
- AST parsing errors (SyntaxError): always log with `logger.warning()` and return an empty result object (never None). Callers should not need null checks.
- External I/O errors (file read, subprocess): log warning, skip the file, continue processing.

### Source module structure
1. Module docstring
2. `from __future__ import annotations`
3. Standard library imports
4. Third-party imports
5. Local imports
6. Constants
7. Public classes/functions
8. Private helpers (prefixed with `_`)

### Test patterns
- Every source file in `src/pyxus/` has a matching test file in `tests/` (mirrored structure)
- All test files use class-based grouping (`class TestFeatureName:`)
- Test data builders use `_make_` prefix: `_make_store()`, `_make_extraction()`, `_make_source_file()`
- Test utility functions (extracting/querying results) use `_extract_` or other descriptive prefix
- Shared helpers live in `tests/helpers.py` (public names, no underscore); file-specific helpers stay local
- Use `@pytest.fixture` only when setup/teardown side effects are needed (e.g., cache reset, autouse)
- Pure data construction uses `_make_` helpers, not fixtures
- Assertions: prefer `assert x == expected` for exact checks, `assert x in collection` for membership
- Every test verifies all relevant output fields, not just one
