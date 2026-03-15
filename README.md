<div align="center">

# Pyxus

**Python Code Intelligence Engine**

Give your AI agents a complete understanding of any Python codebase — in seconds.

[![CI](https://github.com/RayverAimar/pyxus/actions/workflows/ci.yml/badge.svg)](https://github.com/RayverAimar/pyxus/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)

</div>

---

Pyxus builds a **knowledge graph** of your Python codebase — every class, function, method call, import, and inheritance chain — and exposes it to AI agents via [MCP](https://modelcontextprotocol.io/). Your LLM stops guessing and starts *knowing* how the code connects.

**100 files in ~1.2s** | **70-85% call resolution without type hints** | **279 tests**

## The Problem

AI agents read files one at a time. They grep, they guess. But they don't see how code connects — so they miss callers, break dependencies, and write incomplete refactors.

## The Solution

```bash
pyxus analyze /path/to/project   # Build the graph once
pyxus serve                       # Expose it to your AI agent
```

Now your agent has instant answers:

```
You: "What breaks if I change UserService?"

Agent → context("UserService")
  Called by: auth.views.register(), signals.on_user_created(), admin.bulk_create()
  Methods: create(), update(), delete()
  Extends: BaseService
  Risk: HIGH — used in auth pipeline
```

## Installation

```bash
git clone https://github.com/RayverAimar/pyxus.git
cd pyxus && uv sync
```

## MCP Tools

| Tool | What it does |
|------|-------------|
| `context(name)` | Everything about a symbol: callers, callees, imports, inheritance |
| `impact(target)` | Blast radius: what depends on this and what breaks |
| `search(query)` | Find symbols by name with relevance ranking |
| `imports()` | Module dependency graph and circular import detection |

Add to Claude Code (`~/.claude/mcp_servers.json`):

```json
{
  "pyxus": {
    "command": "pyxus",
    "args": ["serve"]
  }
}
```

## CLI

```bash
pyxus analyze <path>    # Full analysis: symbols, imports, hierarchy, calls
pyxus imports <path>    # Fast: import dependencies + circular detection
pyxus status <path>     # Index metadata
pyxus clean <path>      # Delete .pyxus/ index
pyxus serve             # Start MCP server
```

## Import Analysis

A fast mode that maps module dependencies and catches circular imports — useful for understanding coupling and untangling dependency chains before refactoring:

```bash
pyxus imports /path/to/project
```

```
  Modules: 47
  Dependencies: 128

  Circular imports detected: 1
    config → utils → helpers → config
```

Know which modules are tightly coupled, which are isolated, and where the dependency cycles live — before your agent touches a single line.

## What It Resolves

Pyxus tracks what objects each variable points to across function boundaries — no type hints needed:

```python
def get_service():
    return Service()

s = get_service()   # Pyxus knows s is a Service
s.process()         # Resolves to Service.process
```

Constructor returns, parameter bridging, return type chains, MRO inheritance, callable attributes, super() resolution, and closure propagation — all resolved statically.

## Development

```bash
uv sync                              # Install
uv run pytest -x -q                  # 279 tests, ~1.5s
uv run ruff check . && uv run ruff format .
```

## License

MIT
