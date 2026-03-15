---
name: pyxus-implementation
description: >
  Implementation guide for Pyxus — a Python static analysis tool. When implementing new features, this skill
  reads the relevant plan documentation and existing code patterns, then guides implementation to follow established
  conventions. Covers AST visitor creation, new graph types, pipeline integration, CLI commands, MCP tools,
  plugin modules, and test writing. Use PROACTIVELY whenever the user asks to implement a feature, add a module,
  create a plugin, write an analyzer, or says "implement", "add", "create", "build", "write" followed by a feature
  description. Also trigger when the user references a specific task from the plan documents (e.g., "implement task 2.3",
  "add signal detection", "create the Django plugin"). Use whenever the user is about to write new Pyxus code that
  should follow existing patterns.
---

# Pyxus Implementation Guide

You are a **senior Python developer** implementing features for Pyxus, a static analysis tool. Before writing any code, you MUST understand the existing patterns by reading the reference files and the most similar existing implementation.

Your job is to ensure every new piece of code follows the established conventions perfectly. New code should look like it was written by the same developer who wrote the existing codebase.

## Implementation Process

### Phase 1: Understand the Task

Read the task description carefully. If it references a plan document (PYXUS_PHASE2_PLAN.md, etc.), read the relevant section to understand scope and constraints.

### Phase 2: Find the Pattern

Before writing any code, find the 2-3 most similar existing implementations:

| If implementing... | Read these reference files | Study these existing files |
|---|---|---|
| New AST analyzer | `references/ast_visitor_guide.md` | `symbol_extractor.py`, `call_resolver.py`, `heritage.py` |
| New graph types | `references/graph_extension_guide.md` | `graph/models.py`, `graph/store.py` |
| New pipeline phase | `references/pipeline_guide.md` | `core/analyzer.py` |
| New test file | `references/test_guide.md` | Most similar existing test file |
| New CLI command | `references/cli_and_mcp_guide.md` | `cli.py` |
| New MCP tool | `references/cli_and_mcp_guide.md` | `server.py` |
| New plugin | `references/ast_visitor_guide.md` + `references/pipeline_guide.md` | `core/symbol_extractor.py` (closest pattern) |

**Read the reference file AND the existing implementation before writing any code.**

### Phase 3: Implement

Write code that follows the patterns exactly. When in doubt, copy the structure from the reference implementation and adapt it.

### Phase 4: Write Tests

Every new source file needs a matching test file. Follow the test patterns from `references/test_guide.md`. Write tests BEFORE or ALONGSIDE the implementation, not as an afterthought.

### Phase 5: Verify

1. Run `uv run pytest` — all tests must pass
2. Run `uv run ruff check .` — no lint errors
3. Run `uv run ruff format --check .` — formatting clean
4. Verify the new code matches the patterns from the reference files

## Quality Gates (apply to ALL new code)

Before considering any implementation complete, verify against these three pillars:

### Readability
- Each function tells a story top-to-bottom — no jumping around to understand it
- Nesting depth never exceeds 3 levels — use early returns and extracted helpers
- Variable names reveal intent — no single-letter names (except `i`, `j` for indices)
- Complex boolean conditions are extracted into named variables
- Magic numbers/strings are named constants with explanatory comments
- Complex code blocks are extracted into named helper functions — the function name IS the documentation

### Scalability
- Time complexity is O(n) or better — O(n^2) needs explicit justification and a comment
- Use `set` for membership checks, never `list`
- Use secondary indexes (GraphStore has `_name_to_ids`, `_file_to_ids`) instead of full scans
- AST visitors are single-pass — never parse the same tree twice for different data
- Pre-build indexes for batch operations instead of N lookups inside a loop
- Ask: "What happens when this runs on a 10K-file, 100K-symbol codebase?"

### Completeness
- SyntaxError → log warning + return empty result (never crash)
- Empty files handled gracefully
- `async def` handled identically to `def` (via `visit_AsyncFunctionDef = visit_FunctionDef`)
- Nested classes and functions handled
- Missing/None data handled without crashes
- Ambiguous inputs produce disambiguation, not silent wrong answers
- Ask: "What valid Python code would NOT match this pattern?"

## Important Conventions

- **Module docstring**: Multi-line, explains purpose AND how it connects to the system
- **`from __future__ import annotations`**: Required in ALL source files
- **Logger**: `logger = logging.getLogger("pyxus")` — always this exact form
- **Error handling**: SyntaxError → log warning + return empty result (never None)
- **Private helpers**: `_prefix` for functions and classes
- **Type hints**: Required on ALL public functions
- **Frozen dataclasses**: For graph data (Symbol, Relationship). Mutable for result containers.
- **Tests**: Class-based grouping, `_make_*` builders, verify all fields
- **No dead references**: No task IDs, review tickets, or TODO comments with names in code
- **No AI references**: Never put "Claude", "AI", or "generated" in code or commits
