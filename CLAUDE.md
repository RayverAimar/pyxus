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
- **Linting/formatting**: `ruff` (line-length 120, py312 target, rules: E, F, I, UP, B, SIM, RUF, PERF, PIE, LOG, C4, S)
- **Testing**: `pytest` (90% coverage threshold)

## Commands

```bash
uv sync                       # Install dependencies
uv run pytest -x -q           # Run tests (fast)
uv run ruff check .           # Lint
uv run ruff format .          # Format
uv run pyxus analyze <path>   # Analyze a Python project
uv run pyxus serve            # Start MCP server
git config core.hooksPath .githooks                      # Install pre-commit hook (once after clone)
cp -r .claude/skills/* ~/.claude/skills/                  # Install Claude Code skills (once after clone)
```

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
├── intelligence/           # Higher-level analysis (Phase 3)
└── plugins/                # Framework-specific analyzers (Phase 2)
    ├── django/
    ├── celery/
    └── fastapi/
```

## Key data model

- **Symbols**: MODULE, CLASS, METHOD, FUNCTION, PROPERTY, CLASSMETHOD, STATICMETHOD
- **Relationships**: DEFINES, HAS_METHOD, CALLS, IMPORTS, EXTENDS (more added per phase)
- **Symbol ID format**: `{kind}:{file_path}:{name}:{line}`
- Symbols and Relationships are frozen dataclasses (hashable, immutable)

## Workflow rules

- After implementing any feature, run `uv run pytest -x -q` and `uv run ruff check .` BEFORE reporting done. If either fails, fix and re-run.
- Never commit unless the user explicitly asks.
- When implementing, read the 2-3 most similar existing files FIRST. Copy their structure, then adapt. Do not invent new patterns.
- When a task involves multiple files (source + tests), implement both in the same session.
- If implementation is ambiguous, ask before proceeding.

## Conventions (quick reference)

- Code in English; planning docs in Spanish
- src layout (`src/pyxus/`), tests mirror source in `tests/`
- All public functions need type hints
- Double quote style
- `from __future__ import annotations` in all source files (not test files)
- `logger = logging.getLogger("pyxus")` — always this exact form
- SyntaxError → log warning + return empty result (never None)
- Frozen `@dataclass` for graph data; regular `@dataclass` for result containers
- Private helpers: `_snake_case()`; private classes: `_ClassName`; constants: `UPPER_CASE`
- Tests: class-based grouping, `_make_*` builders, verify all output fields
- No AI references in commits. No dead references (task IDs, review comments) in code.

For detailed patterns and examples, see the `pyxus-code-review` and `pyxus-implementation` skills.
