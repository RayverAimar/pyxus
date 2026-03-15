# Rule 7: Readability, Scalability, and Completeness

Code that works is not enough. It must be understandable by another developer in 6 months, handle edge cases gracefully, and not become a bottleneck as the codebase grows. These three qualities — readability, scalability, and completeness — are what separate production code from prototypes.

## Readability: "Can another developer understand this without asking me?"

### Functions should tell a story

A function should read top-to-bottom like a narrative. If you need to jump around to understand what's happening, the function needs restructuring.

```python
# BAD — you have to mentally track state across 30 lines
def resolve_callee(site, ag, symbol_index, id_to_info):
    if site.callee_name in symbol_index:
        return symbol_index[site.callee_name]
    if "." not in site.callee_name:
        return None
    obj_name, attr_name = site.callee_name.rsplit(".", 1)
    obj_ns = f"{site.caller_ns}.{obj_name}"
    for pointee in ag.get_pointees(obj_ns):
        info = id_to_info.get(pointee)
        if info and info[0] == SymbolKind.CLASS:
            qualified = f"{info[1]}.{attr_name}"
            if qualified in symbol_index:
                return symbol_index[qualified]
    if "." in obj_name:
        parts = obj_name.split(".")
        current_ns = f"{site.caller_ns}.{parts[0]}"
        for part in parts[1:]:
            pointees = ag.get_pointees(current_ns)
            resolved_next = False
            for pointee in pointees:
                info = id_to_info.get(pointee)
                if info and info[0] == SymbolKind.CLASS:
                    current_ns = f"{pointee}.{part}"
                    resolved_next = True
                    break
            if not resolved_next:
                break
        else:
            for pointee in ag.get_pointees(current_ns):
                info = id_to_info.get(pointee)
                if info and info[0] == SymbolKind.CLASS:
                    qualified = f"{info[1]}.{attr_name}"
                    if qualified in symbol_index:
                        return symbol_index[qualified]
    return None

# GOOD — strategies are named and separated
def _resolve_callee(site, ag, symbol_index, id_to_info):
    """Try to resolve a call site to a target symbol ID.

    Strategy 1: Direct name match in the symbol index.
    Strategy 2: Follow the assignment graph for variable-based calls.
    """
    # Strategy 1: direct match
    if site.callee_name in symbol_index:
        return symbol_index[site.callee_name]

    if "." not in site.callee_name:
        return None

    obj_name, attr_name = site.callee_name.rsplit(".", 1)
    obj_ns = f"{site.caller_ns}.{obj_name}"

    # Strategy 2a: direct AG lookup
    for pointee in ag.get_pointees(obj_ns):
        resolved = _try_class_method(pointee, attr_name, id_to_info, symbol_index)
        if resolved:
            return resolved

    # Strategy 2b: step-by-step for dotted objects (e.g., self._conn.send)
    if "." in obj_name:
        return _resolve_dotted_callee(obj_name, attr_name, site, ag, id_to_info, symbol_index)

    return None
```

**Key principle:** Extract named helper functions when a block of code implements a distinct strategy. The function name IS the documentation.

### Nesting depth > 3 is a red flag

```python
# BAD — 5 levels of nesting
for file in files:
    if file.is_python:
        for cls in file.classes:
            if cls.has_bases:
                for base in cls.bases:
                    if base in known_classes:
                        # What are we even doing here?
                        process(base)

# GOOD — early returns and extracted functions reduce nesting
for file in files:
    if not file.is_python:
        continue
    _process_class_bases(file.classes, known_classes)

def _process_class_bases(classes, known_classes):
    for cls in classes:
        for base in cls.bases:
            if base in known_classes:
                process(base)
```

### Variable names should reveal intent

```python
# BAD — single letters, abbreviations
for s in g.symbols():
    if s.kind == SymbolKind.CLASS:
        ms = g.successors_by_kind(s.id, RelationKind.HAS_METHOD)
        for m in ms:
            r = _check(m)

# GOOD — names reveal what the code does
for symbol in graph.symbols():
    if symbol.kind == SymbolKind.CLASS:
        methods = graph.successors_by_kind(symbol.id, RelationKind.HAS_METHOD)
        for method in methods:
            result = _check_method_signature(method)
```

**Exceptions:** `i`, `j` for loop indices. `x`, `y` for coordinates. `f` for file handles. These are universally understood.

### Boolean conditions should read like English

```python
# BAD — you have to decode the logic
if not (sym.kind != SymbolKind.MODULE and not sym.name.startswith("_")):
    continue

# GOOD — reads like a sentence
is_private = sym.name.startswith("_")
is_module = sym.kind == SymbolKind.MODULE
if is_module or is_private:
    continue
```

### Magic numbers and strings need names

```python
# BAD — what does 10 mean? what does 0.01 mean?
if depth > 10:
    break
score += min(count * 0.01, 0.1)

# GOOD — constants explain the domain
MAX_TRAVERSAL_DEPTH = 10
_SCORE_EDGE_BOOST = 0.01
_SCORE_EDGE_BOOST_CAP = 0.1

if depth > MAX_TRAVERSAL_DEPTH:
    break
score += min(count * _SCORE_EDGE_BOOST, _SCORE_EDGE_BOOST_CAP)
```

## Scalability: "What happens when this runs on a 10K-file codebase?"

### O(n) is fine, O(n^2) needs justification

```python
# BAD — O(n^2) — for each symbol, scan all symbols
def find_duplicates(graph):
    duplicates = []
    symbols = graph.symbols()
    for s1 in symbols:
        for s2 in symbols:
            if s1.id != s2.id and s1.name == s2.name:
                duplicates.append((s1, s2))
    return duplicates

# GOOD — O(n) — build index, then find collisions
def find_duplicates(graph):
    by_name = defaultdict(list)
    for symbol in graph.symbols():
        by_name[symbol.name].append(symbol)
    return {name: syms for name, syms in by_name.items() if len(syms) > 1}
```

### Use secondary indexes instead of full scans

GraphStore already maintains `_name_to_ids` and `_file_to_ids` to avoid O(n) scans. New code should use these:

```python
# BAD — full graph scan to find symbols by file
symbols_in_file = [s for s in graph.symbols() if s.file_path == target_file]

# GOOD — O(k) where k is symbols in that file
symbols_in_file = graph.get_symbols_in_file(target_file)
```

**When adding a new lookup pattern:** If the same query will be called repeatedly, consider adding a secondary index to GraphStore rather than scanning.

### AST visitors should be single-pass

```python
# BAD — parsing the AST twice for the same information
tree = ast.parse(source)
classes = _extract_classes(tree)  # walks AST
methods = _extract_methods(tree)  # walks AST again

# GOOD — single visitor collects everything
tree = ast.parse(source)
visitor = _SymbolVisitor(file_path)
visitor.visit(tree)  # one pass: collects classes AND methods
```

### Data structures matter

```python
# BAD — list for membership checks (O(n) per lookup)
visited = []
if node_id not in visited:  # O(n)
    visited.append(node_id)

# GOOD — set for membership checks (O(1) per lookup)
visited: set[str] = set()
if node_id not in visited:  # O(1)
    visited.add(node_id)
```

### Pre-build indexes for batch operations

```python
# BAD — N lookups inside a loop
for call_site in call_sites:
    for symbol in graph.symbols():  # O(n) per call site = O(n*m) total
        if symbol.name == call_site.callee_name:
            ...

# GOOD — build index once, then O(1) lookups
symbol_index = _build_symbol_index(graph)  # O(n) once
for call_site in call_sites:
    if call_site.callee_name in symbol_index:  # O(1) per call site
        ...
```

## Completeness: "What happens when the input is weird?"

### Every AST analyzer must handle these cases

1. **SyntaxError** — file doesn't parse → log warning, return empty result
2. **Empty file** — no classes, no functions → produce only MODULE symbol
3. **Files with only imports** — no definitions → produce only MODULE symbol
4. **Async functions** — `async def` must be handled identically to `def`
5. **Nested classes** — `class Outer: class Inner:` → both extracted
6. **Decorators with arguments** — `@action(detail=True)` → decorator name is `"action"`
7. **Star imports** — `from module import *` → log, skip (can't resolve)
8. **Circular imports** — A imports B imports A → must not infinite loop
9. **Very long files** — 10K+ lines → must not be significantly slower

### Every graph operation must handle missing data

```python
# BAD — assumes symbol exists
symbol = graph.get_symbol(symbol_id)
print(symbol.name)  # AttributeError if not found

# GOOD — handles None
symbol = graph.get_symbol(symbol_id)
if symbol is None:
    return {"error": f"Symbol not found: {symbol_id}"}
```

### Disambiguation over silent wrong answers

```python
# BAD — picks the first match silently (might be wrong)
matches = graph.get_symbol_by_name(name)
symbol = matches[0]  # Which "create"? The one in Service or in Repository?

# GOOD — asks when ambiguous
matches = graph.get_symbol_by_name(name)
matches = [m for m in matches if m.kind != SymbolKind.MODULE]
if len(matches) > 1:
    return _disambiguation_response(matches)
symbol = matches[0]
```

### Think about what DOESN'T match

When writing pattern detection, always ask: "What valid Python code would NOT match this pattern?"

```python
# BAD — only handles @receiver decorator
def detect_signals(node):
    for decorator in node.decorator_list:
        if get_dotted_name(decorator) == "receiver":
            # Found one!
            ...
    # What about signal.connect(handler)? Missed!

# GOOD — handles both patterns
def detect_signals(node):
    # Pattern 1: @receiver(signal, sender=Model) decorator
    for decorator in node.decorator_list:
        ...
    # Pattern 2: signal.connect(handler, sender=Model) call
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            ...
```

## Review checklist

For every change, ask these questions:

### Readability
- [ ] Can I understand each function without reading its callers?
- [ ] Are there more than 3 levels of nesting? If so, can we flatten?
- [ ] Do variable names reveal intent? (No single letters except `i`, `j`)
- [ ] Are boolean conditions readable as English sentences?
- [ ] Are magic numbers/strings extracted to named constants?
- [ ] Are complex blocks extracted into named helper functions?

### Scalability
- [ ] What is the time complexity? Is O(n^2) justified?
- [ ] Are we using secondary indexes instead of full scans?
- [ ] Are AST visitors single-pass?
- [ ] Are we using `set` for membership checks, not `list`?
- [ ] Would this be noticeably slow on a 10K-file codebase?

### Completeness
- [ ] SyntaxError handled? Empty file handled?
- [ ] Async functions handled identically to sync?
- [ ] Nested classes/functions handled?
- [ ] Missing/None data handled without crashes?
- [ ] Ambiguous inputs produce disambiguation, not wrong answers?
- [ ] What valid Python code would NOT match this pattern?
