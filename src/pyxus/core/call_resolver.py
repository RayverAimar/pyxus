"""Assignment graph engine for inter-procedural call resolution.

Inspired by PyCG (ICSE 2021), this module resolves function and method calls
without requiring type hints. The core insight: by tracking what objects each
variable can point to across function boundaries, we can determine the target
of calls like ``obj.save()`` even when ``obj``'s type isn't annotated.

The algorithm:
1. Build an initial assignment graph from all files.
2. Iterate until no new edges are added (fixed-point):
   - [ASSIGN] ``x = expr`` → x points to whatever expr evaluates to
   - [CALL]   ``f(arg)`` → connect arg to f's parameter inter-procedurally
   - [NEW]    ``X()`` → creates instance, links to X's __init__
   - [ATTR]   ``o.x`` → resolve x through class hierarchy of o's type
   - [RETURN] ``return expr`` → connect to caller's assignment target
3. Extract CALLS edges from the final assignment graph.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field

from pyxus.core.ast_utils import get_dotted_name
from pyxus.core.file_walker import SourceFile
from pyxus.core.heritage import ClassHierarchy
from pyxus.graph.models import (
    CallReason,
    RelationKind,
    Relationship,
    SymbolKind,
    make_relationship_id,
)
from pyxus.graph.store import GraphStore

logger = logging.getLogger("pyxus")

# Typical codebases converge in 2-4 iterations; 10 is a safe upper bound
# that prevents runaway loops on pathological assignment cycles.
MAX_ITERATIONS = 10

# Maximum BFS depth when resolving transitive pointees in the assignment graph.
# Independent of MAX_ITERATIONS — this governs a single get_pointees() call.
MAX_POINTEE_DEPTH = 10


@dataclass
class UnresolvedCall:
    """A call site that could not be resolved to a target function."""

    file_path: str
    line: int
    call_text: str
    reason: CallReason


@dataclass
class ResolutionStats:
    """Aggregate statistics about call resolution."""

    total_calls: int = 0
    resolved: int = 0
    external: int = 0
    unresolved_by_reason: dict[CallReason, int] = field(default_factory=dict)

    @property
    def internal_calls(self) -> int:
        """Calls that target symbols in the repo (resolved + unresolved internal)."""
        return self.total_calls - self.external

    @property
    def internal_resolution_rate(self) -> float:
        """Resolution rate considering only intra-repo calls."""
        internal = self.internal_calls
        return self.resolved / internal if internal > 0 else 0.0


@dataclass
class CallResolutionResult:
    """Complete output of the call resolution pass."""

    relationships: list[Relationship]
    unresolved: list[UnresolvedCall]
    stats: ResolutionStats


class AssignmentGraph:
    """Tracks what objects each variable can point to.

    Each node is identified by a namespace path (e.g., "mod.MyClass.method.x").
    An edge from A to B means "A can point to whatever B points to".
    """

    def __init__(self) -> None:
        self._edges: dict[str, set[str]] = {}

    def add_edge(self, source: str, target: str) -> bool:
        """Add an assignment edge. Returns True if the edge is new."""
        if source not in self._edges:
            self._edges[source] = set()
        if target in self._edges[source]:
            return False
        self._edges[source].add(target)
        return True

    def get_direct_targets(self, source: str) -> set[str]:
        """Get the direct targets of a name (non-transitive)."""
        return self._edges.get(source, set())

    def get_pointees(self, source: str, max_depth: int = MAX_POINTEE_DEPTH) -> set[str]:
        """Transitively follow assignment edges to find all concrete objects.

        Uses BFS with a depth limit to handle cycles safely. A node is
        "concrete" if it has no unvisited outgoing edges (leaf or cycle endpoint).
        """
        result: set[str] = set()
        visited: set[str] = set()
        frontier = {source}
        depth = 0

        while frontier and depth < max_depth:
            next_frontier: set[str] = set()
            for node in frontier:
                if node in visited:
                    continue
                visited.add(node)
                # Only follow edges to nodes we haven't seen yet
                unvisited_targets = self._edges.get(node, set()) - visited
                if not unvisited_targets:
                    result.add(node)
                else:
                    next_frontier.update(unvisited_targets)
            frontier = next_frontier
            depth += 1

        return result

    @property
    def edge_count(self) -> int:
        return sum(len(targets) for targets in self._edges.values())


# ── Public API ─────────────────────────────────────────────────────────


def resolve_calls(
    files: list[SourceFile],
    graph: GraphStore,
    class_hierarchy: ClassHierarchy,
) -> CallResolutionResult:
    """Resolve all function/method calls using assignment graph analysis.

    Runs the fixed-point iteration over all source files, then extracts CALLS edges.
    """
    ag = AssignmentGraph()
    symbol_index = _build_symbol_index(graph)

    # symbol_id → (kind, name) for O(1) lookup during resolution
    id_to_info: dict[str, tuple[SymbolKind, str]] = {}
    # module namespace → symbol_id for enclosing symbol lookup
    module_ns_index: dict[str, str] = {}
    for sym in graph.symbols():
        if sym.kind == SymbolKind.MODULE:
            module_ns_index[_module_ns(sym.file_path)] = sym.id
        else:
            id_to_info[sym.id] = (sym.kind, sym.name)

    # Seed constructor returns: MyClass() returns an instance of MyClass.
    # Without this, `x = MyClass(); x.method()` can never resolve because
    # MyClass.__return__ has no edges in the assignment graph.
    for sym_id, info in id_to_info.items():
        if info[0] == SymbolKind.CLASS:
            ag.add_edge(f"{sym_id}.__return__", sym_id)

    # Build per-file import aliases so that `from models import User` maps
    # the local name `User` to the actual symbol ID from models.py
    file_symbol_indexes = _build_per_file_indexes(files, symbol_index, graph)

    # Phase 1: Seed the assignment graph from all files
    call_sites: list[_CallSite] = []
    for source_file in files:
        try:
            tree = ast.parse(source_file.content, filename=source_file.path)
        except SyntaxError as e:
            logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
            continue

        file_index = file_symbol_indexes.get(source_file.path, symbol_index)
        collector = _AssignmentCollector(source_file.path, ag, file_index)
        collector.visit(tree)
        call_sites.extend(collector.call_sites)

    # Phase 2: Fixed-point iteration — propagate assignments until stable
    for iteration in range(MAX_ITERATIONS):
        new_edges = 0
        for source_file in files:
            try:
                tree = ast.parse(source_file.content, filename=source_file.path)
            except SyntaxError as e:
                logger.warning("Syntax error in %s (line %s): %s", source_file.path, e.lineno, e.msg)
                continue
            file_index = file_symbol_indexes.get(source_file.path, symbol_index)
            propagator = _AssignmentPropagator(source_file.path, ag, file_index)
            propagator.visit(tree)
            new_edges += propagator.new_edges

        if new_edges == 0:
            logger.debug("Assignment graph converged after %d iterations", iteration + 1)
            break
    else:
        logger.warning("Assignment graph did not converge after %d iterations", MAX_ITERATIONS)

    # Phase 3: Extract CALLS edges from resolved call sites
    resolver = _CallResolver(ag, symbol_index, id_to_info, module_ns_index, class_hierarchy)
    return resolver.extract_call_edges(call_sites)


# ── Index builders ─────────────────────────────────────────────────────


def _build_symbol_index(graph: GraphStore) -> dict[str, str]:
    """Build a lookup from simple/qualified names to symbol IDs.

    Single pass over all symbols. Creates entries like:
    - "ProfileService" → "class:services/profiles.py:ProfileService:1"
    - "ProfileService.create" → "staticmethod:services/profiles.py:create:3"
    - "class:services/profiles.py:ProfileService:1.create" → (same, ID-keyed)

    Name-based entries (bare and "ClassName.method") are pruned on collision
    to avoid wrong attribution. ID-based entries ("{class_id}.method") are
    always unique and used by the resolver for AG-resolved calls.
    """
    index: dict[str, str] = {}
    # Track names seen more than once to avoid wrong attribution
    name_counts: dict[str, int] = {}

    for symbol in graph.symbols():
        if symbol.kind == SymbolKind.MODULE:
            continue

        name_counts[symbol.name] = name_counts.get(symbol.name, 0) + 1
        # Only set bare name if unambiguous (first occurrence)
        if name_counts[symbol.name] == 1:
            index[symbol.name] = symbol.id
        elif name_counts[symbol.name] == 2:
            # Second occurrence — remove the bare name to avoid wrong attribution
            index.pop(symbol.name, None)

        if symbol.kind in (SymbolKind.METHOD, SymbolKind.STATICMETHOD, SymbolKind.CLASSMETHOD, SymbolKind.PROPERTY):
            owners = graph.predecessors_by_kind(symbol.id, RelationKind.HAS_METHOD)
            for owner in owners:
                # Name-based: "ClassName.method" — prune on collision
                qualified = f"{owner.name}.{symbol.name}"
                name_counts[qualified] = name_counts.get(qualified, 0) + 1
                if name_counts[qualified] == 1:
                    index[qualified] = symbol.id
                elif name_counts[qualified] == 2:
                    index.pop(qualified, None)

                # ID-based: "{class_symbol_id}.method" — always unique
                index[f"{owner.id}.{symbol.name}"] = symbol.id

    return index


def _build_per_file_indexes(
    files: list[SourceFile],
    global_index: dict[str, str],
    graph: GraphStore,
) -> dict[str, dict[str, str]]:
    """Build per-file symbol indexes that include file-local symbols and import aliases.

    For each file, the index contains: global symbols + symbols defined in this
    file + imported symbols. File-local symbols override the global index, which
    ensures that globally-ambiguous names (e.g., a class name shared across files)
    still resolve correctly within their own file.
    """
    # Build a lookup: (file_path, symbol_name) → symbol_id for all symbols
    file_name_to_id: dict[tuple[str, str], str] = {}
    for sym in graph.symbols():
        if sym.kind != SymbolKind.MODULE:
            file_name_to_id[(sym.file_path, sym.name)] = sym.id

    # Group by file for O(1) lookup during per-file index construction
    file_local_symbols: dict[str, dict[str, str]] = {}
    for (fpath, name), sym_id in file_name_to_id.items():
        if fpath not in file_local_symbols:
            file_local_symbols[fpath] = {}
        file_local_symbols[fpath][name] = sym_id

    # Build module_path → file_path mapping (for resolving import targets)
    from pyxus.core.import_resolver import build_file_index

    module_to_file = build_file_index(files)

    result: dict[str, dict[str, str]] = {}

    for source_file in files:
        try:
            tree = ast.parse(source_file.content, filename=source_file.path)
        except SyntaxError:
            continue

        import_aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                target_file = module_to_file.get(node.module)
                if target_file:
                    for alias in node.names:
                        local_name = alias.asname or alias.name
                        sym_id = file_name_to_id.get((target_file, alias.name))
                        if sym_id:
                            import_aliases[local_name] = sym_id

            elif isinstance(node, ast.ImportFrom) and node.level > 0:
                # Relative import: resolve relative to current file's package
                from pathlib import PurePosixPath

                parts = list(PurePosixPath(source_file.path).parts[:-1])
                steps_up = node.level - 1
                if steps_up <= len(parts):
                    if steps_up > 0:
                        parts = parts[:-steps_up]
                    module = node.module or ""
                    target_module = ".".join(parts + module.split(".")) if module else ".".join(parts)
                    target_file = module_to_file.get(target_module)
                    if target_file:
                        for alias in node.names:
                            local_name = alias.asname or alias.name
                            sym_id = file_name_to_id.get((target_file, alias.name))
                            if sym_id:
                                import_aliases[local_name] = sym_id

        # Merge: global < file-local < imports (most specific wins)
        locals_for_file = file_local_symbols.get(source_file.path, {})
        if locals_for_file or import_aliases:
            merged = dict(global_index)
            merged.update(locals_for_file)
            merged.update(import_aliases)
            result[source_file.path] = merged

    return result


# ── AST helpers ────────────────────────────────────────────────────────


def _module_ns(file_path: str) -> str:
    """Convert a file path to a module namespace string."""
    return file_path.replace("\\", ".").replace("/", ".").removesuffix(".py")


def _get_call_name(node: ast.Call) -> str | None:
    """Extract the callee name from a Call node (e.g., "obj.method" from obj.method())."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        value_name = get_dotted_name(node.func.value)
        if value_name:
            return f"{value_name}.{node.func.attr}"
    return None


def _get_assign_target_name(node: ast.expr) -> str | None:
    """Extract the name from an assignment target (e.g., "self.x" from self.x = ...)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = get_dotted_name(node.value)
        if prefix:
            return f"{prefix}.{node.attr}"
    return None


def _resolve_expr(node: ast.expr, current_ns: str, symbol_index: dict[str, str]) -> str | None:
    """Resolve an AST expression to a namespace string in the assignment graph."""
    if isinstance(node, ast.Name):
        if node.id in symbol_index:
            return symbol_index[node.id]
        return f"{current_ns}.{node.id}"

    if isinstance(node, ast.Attribute):
        obj_ns = _resolve_expr(node.value, current_ns, symbol_index)
        if obj_ns:
            return f"{obj_ns}.{node.attr}"

    if isinstance(node, ast.Call):
        func_name = _get_call_name(node)
        if func_name and func_name in symbol_index:
            return f"{symbol_index[func_name]}.__return__"

    return None


# ── Internal data ──────────────────────────────────────────────────────


@dataclass
class _CallSite:
    """A call expression found in source code, pending resolution."""

    file_path: str
    line: int
    caller_ns: str
    callee_name: str
    call_text: str


# ── AST visitors ───────────────────────────────────────────────────────


class _NamespaceTrackingVisitor(ast.NodeVisitor):
    """Base class that tracks the current namespace as it walks the AST.

    Maintains a stack of scope names (module → class → function) and a
    class stack to distinguish methods from closures inside methods.
    """

    def __init__(self, file_path: str) -> None:
        self._ns_stack: list[str] = [_module_ns(file_path)]
        self._class_stack: list[str] = []

    @property
    def _current_ns(self) -> str:
        return ".".join(self._ns_stack)

    @property
    def _inside_class(self) -> bool:
        """True when the immediate enclosing scope is a class (not a function)."""
        return bool(self._class_stack) and self._ns_stack[-1] != self._class_stack[-1]

    @property
    def _enclosing_class_name(self) -> str | None:
        return self._class_stack[-1] if self._class_stack else None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._ns_stack.append(node.name)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()
        self._ns_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._ns_stack.append(node.name)
        self.generic_visit(node)
        self._ns_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_For(self, node: ast.For) -> None:
        """Connect loop variable to iterable so `for x in items: x.method()` can resolve."""
        self.generic_visit(node)


class _AssignmentCollector(_NamespaceTrackingVisitor):
    """First pass: collect assignments and call sites from the AST."""

    def __init__(self, file_path: str, ag: AssignmentGraph, symbol_index: dict[str, str]) -> None:
        super().__init__(file_path)
        self.file_path = file_path
        self.ag = ag
        self.symbol_index = symbol_index
        self.call_sites: list[_CallSite] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._ns_stack.append(node.name)

        class_name = self._enclosing_class_name
        is_method = bool(class_name and class_name in self.symbol_index and node.args.args)

        # Seed self/cls parameter with the enclosing class (not for closures)
        if is_method:
            first_param = node.args.args[0].arg
            param_ns = f"{self._current_ns}.{first_param}"
            self.ag.add_edge(param_ns, self.symbol_index[class_name])

        # Bridge the two namespace systems: the AST visitor uses module-path
        # namespaces (e.g., "test.process.obj") but call sites use symbol-ID
        # namespaces (e.g., "function:test.py:process:5.param_0"). Without
        # this bridge, inter-procedural param/return propagation is broken.
        func_id = self._lookup_func_id(node.name, class_name)
        if func_id:
            # Return: symbol-ID.__return__ → module-path.__return__
            self.ag.add_edge(f"{func_id}.__return__", f"{self._current_ns}.__return__")

            # Params: module-path.param_name → symbol-ID.param_i
            # For methods, skip self/cls (index 0) — call sites don't include it
            param_offset = 1 if is_method else 0
            for i, arg in enumerate(node.args.args[param_offset:]):
                self.ag.add_edge(f"{self._current_ns}.{arg.arg}", f"{func_id}.param_{i}")

        self.generic_visit(node)
        self._ns_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _lookup_func_id(self, func_name: str, class_name: str | None) -> str | None:
        """Find the symbol ID for a function/method by name."""
        if class_name:
            qualified = f"{class_name}.{func_name}"
            if qualified in self.symbol_index:
                return self.symbol_index[qualified]
        return self.symbol_index.get(func_name)

    def visit_For(self, node: ast.For) -> None:
        target_name = _get_assign_target_name(node.target)
        if target_name:
            target_ns = f"{self._current_ns}.{target_name}"
            iter_ns = _resolve_expr(node.iter, self._current_ns, self.symbol_index)
            if iter_ns:
                self.ag.add_edge(target_ns, iter_ns)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            target_name = _get_assign_target_name(target)
            if target_name:
                target_ns = f"{self._current_ns}.{target_name}"
                value_ns = _resolve_expr(node.value, self._current_ns, self.symbol_index)
                if value_ns:
                    self.ag.add_edge(target_ns, value_ns)

                    # Promote self.attr assignments to class level so other methods
                    # can resolve self.attr.method() via the class namespace
                    class_name = self._enclosing_class_name
                    if class_name and class_name in self.symbol_index and target_name.startswith("self."):
                        class_id = self.symbol_index[class_name]
                        attr = target_name[5:]  # strip "self."
                        self.ag.add_edge(f"{class_id}.{attr}", value_ns)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee_name = _get_call_name(node)
        if callee_name:
            self.call_sites.append(
                _CallSite(
                    file_path=self.file_path,
                    line=node.lineno,
                    caller_ns=self._current_ns,
                    callee_name=callee_name,
                    call_text=callee_name + "()",
                )
            )
            # Connect arguments to parameters inter-procedurally
            callee_id = self.symbol_index.get(callee_name)
            if callee_id and node.args:
                for i, arg in enumerate(node.args):
                    arg_ns = _resolve_expr(arg, self._current_ns, self.symbol_index)
                    if arg_ns:
                        self.ag.add_edge(f"{callee_id}.param_{i}", arg_ns)

                # Constructor calls: MyClass(args) also connects to __init__ params
                # because the call site writes to class_id.param_i but __init__'s
                # bridge reads from method_id.param_i
                init_id = self.symbol_index.get(f"{callee_name}.__init__")
                if init_id:
                    for i, arg in enumerate(node.args):
                        arg_ns = _resolve_expr(arg, self._current_ns, self.symbol_index)
                        if arg_ns:
                            self.ag.add_edge(f"{init_id}.param_{i}", arg_ns)

        self.generic_visit(node)


class _AssignmentPropagator(_NamespaceTrackingVisitor):
    """Subsequent passes: propagate assignments until the graph stabilizes."""

    def __init__(self, file_path: str, ag: AssignmentGraph, symbol_index: dict[str, str]) -> None:
        super().__init__(file_path)
        self.ag = ag
        self.symbol_index = symbol_index
        self.new_edges = 0

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None:
            return_ns = f"{self._current_ns}.__return__"
            value_ns = _resolve_expr(node.value, self._current_ns, self.symbol_index)
            if value_ns and self.ag.add_edge(return_ns, value_ns):
                self.new_edges += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Re-connect arguments to parameters using information from previous iterations."""
        callee_name = _get_call_name(node)
        if callee_name:
            callee_id = self.symbol_index.get(callee_name)
            if callee_id and node.args:
                for i, arg in enumerate(node.args):
                    arg_ns = _resolve_expr(arg, self._current_ns, self.symbol_index)
                    if arg_ns:
                        param_ns = f"{callee_id}.param_{i}"
                        if self.ag.add_edge(param_ns, arg_ns):
                            self.new_edges += 1
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            target_name = _get_assign_target_name(target)
            if target_name:
                target_ns = f"{self._current_ns}.{target_name}"
                value_ns = _resolve_expr(node.value, self._current_ns, self.symbol_index)
                # Fallback: resolve obj.method() return via AG when _resolve_expr
                # can't find the callee directly (e.g., pool.get_conn())
                if not value_ns and isinstance(node.value, ast.Call):
                    value_ns = self._resolve_call_return_via_ag(node.value)
                if value_ns and self.ag.add_edge(target_ns, value_ns):
                    self.new_edges += 1
        self.generic_visit(node)

    def _resolve_call_return_via_ag(self, node: ast.Call) -> str | None:
        """Resolve obj.method() return type by following obj through the AG."""
        call_name = _get_call_name(node)
        if not call_name or "." not in call_name:
            return None
        obj_name, method_name = call_name.rsplit(".", 1)
        obj_ns = f"{self._current_ns}.{obj_name}"
        for pointee in self.ag.get_pointees(obj_ns):
            # ID-based lookup: "{class_symbol_id}.method" — always unique
            id_qualified = f"{pointee}.{method_name}"
            if id_qualified in self.symbol_index:
                return f"{self.symbol_index[id_qualified]}.__return__"
            # Name-based fallback
            parts = pointee.split(":")
            if len(parts) >= 4 and parts[0] == "class":
                name_qualified = f"{parts[2]}.{method_name}"
                if name_qualified in self.symbol_index:
                    return f"{self.symbol_index[name_qualified]}.__return__"
        return None


# ── Call resolution ────────────────────────────────────────────────────


class _CallResolver:
    """Resolves call sites to target symbol IDs and classifies unresolved calls.

    Encapsulates all resolution state (assignment graph, symbol indexes,
    class hierarchy) to avoid passing 5+ parameters through every function.
    """

    def __init__(
        self,
        ag: AssignmentGraph,
        symbol_index: dict[str, str],
        id_to_info: dict[str, tuple[SymbolKind, str]],
        module_ns_index: dict[str, str],
        hierarchy: ClassHierarchy,
    ) -> None:
        self._ag = ag
        self._symbol_index = symbol_index
        self._id_to_info = id_to_info
        self._module_ns_index = module_ns_index
        self._hierarchy = hierarchy

    def extract_call_edges(self, call_sites: list[_CallSite]) -> CallResolutionResult:
        """Convert resolved call sites into CALLS relationships."""
        relationships: list[Relationship] = []
        unresolved: list[UnresolvedCall] = []
        stats = ResolutionStats(total_calls=len(call_sites))
        seen_edges: set[tuple[str, str]] = set()

        for site in call_sites:
            callee_id = self._resolve_callee(site)

            if callee_id:
                caller_id = self._find_enclosing_symbol(site.caller_ns)
                if caller_id and (caller_id, callee_id) not in seen_edges:
                    seen_edges.add((caller_id, callee_id))
                    relationships.append(
                        Relationship(
                            id=make_relationship_id(caller_id, callee_id, RelationKind.CALLS),
                            source_id=caller_id,
                            target_id=callee_id,
                            kind=RelationKind.CALLS,
                        )
                    )
                    stats.resolved += 1
            else:
                reason = self._classify_unresolved(site)
                if reason == CallReason.EXTERNAL:
                    stats.external += 1
                else:
                    unresolved.append(
                        UnresolvedCall(
                            file_path=site.file_path,
                            line=site.line,
                            call_text=site.call_text,
                            reason=reason,
                        )
                    )
                    stats.unresolved_by_reason[reason] = stats.unresolved_by_reason.get(reason, 0) + 1

        return CallResolutionResult(relationships=relationships, unresolved=unresolved, stats=stats)

    def _resolve_callee(self, site: _CallSite) -> str | None:
        """Try to resolve a call site to a target symbol ID.

        Strategy 1: Direct name match in the symbol index.
        Strategy 2: Follow the assignment graph for variable-based calls.
        Strategy 3: super().method() → resolve via MRO of enclosing class.
        """
        if site.callee_name in self._symbol_index:
            return self._symbol_index[site.callee_name]

        if "." not in site.callee_name:
            return None

        obj_name, attr_name = site.callee_name.rsplit(".", 1)

        # Strategy 3: super().method() → resolve to parent class method via MRO
        if obj_name == "super":
            return self._resolve_super_call(site.caller_ns, attr_name)

        obj_ns = f"{site.caller_ns}.{obj_name}"

        # Strategy 2a: Direct AG lookup for the full object path
        for pointee in self._ag.get_pointees(obj_ns):
            resolved = self._try_class_method(pointee, attr_name)
            if resolved:
                return resolved

        # Strategy 2b: Step-by-step resolution for dotted objects (e.g., self._conn.send)
        if "." in obj_name:
            parts = obj_name.split(".")
            current_ns = f"{site.caller_ns}.{parts[0]}"
            for part in parts[1:]:
                pointees = self._ag.get_pointees(current_ns)
                resolved_next = False
                for pointee in pointees:
                    info = self._id_to_info.get(pointee)
                    if info and info[0] == SymbolKind.CLASS:
                        current_ns = f"{pointee}.{part}"
                        resolved_next = True
                        break
                if not resolved_next:
                    break
            else:
                for pointee in self._ag.get_pointees(current_ns):
                    resolved = self._try_class_method(pointee, attr_name)
                    if resolved:
                        return resolved

        return None

    def _resolve_super_call(self, caller_ns: str, method_name: str) -> str | None:
        """Resolve super().method() to the parent class method via MRO."""
        # Find the enclosing class from the namespace (e.g., "mod.MyClass.method" → "MyClass")
        parts = caller_ns.split(".")
        for i in range(len(parts) - 1, 0, -1):
            class_name = parts[i]
            # Try to find the class in the symbol index
            class_id = self._symbol_index.get(class_name)
            if class_id and class_id in self._id_to_info:
                info = self._id_to_info[class_id]
                if info[0] == SymbolKind.CLASS:
                    # Walk MRO starting from index 1 (skip self, start at parent)
                    mro = self._hierarchy.get_mro(class_id)
                    for parent_id in mro[1:]:
                        result = f"{parent_id}.{method_name}"
                        if result in self._symbol_index:
                            return self._symbol_index[result]
                    return None
        return None

    def _try_class_method(self, pointee: str, method_name: str) -> str | None:
        """If pointee is a CLASS, look up its method — walking the MRO if needed.

        Also handles callable attributes: when self.x = some_func is stored
        in __init__, follows the AG edge to resolve the stored callable.
        """
        info = self._id_to_info.get(pointee)
        if not info or info[0] != SymbolKind.CLASS:
            return None

        # Direct lookup: method defined on this class
        id_qualified = f"{pointee}.{method_name}"
        if id_qualified in self._symbol_index:
            return self._symbol_index[id_qualified]

        # Name-based fallback for unambiguous names
        name_qualified = f"{info[1]}.{method_name}"
        if name_qualified in self._symbol_index:
            return self._symbol_index[name_qualified]

        # MRO walk: method inherited from a parent class
        owner_id = self._hierarchy.resolve_attribute(pointee, method_name)
        if owner_id:
            inherited = f"{owner_id}.{method_name}"
            if inherited in self._symbol_index:
                return self._symbol_index[inherited]

        # Callable attribute: self.x = some_func stored via assignment.
        # Follow the AG edge from {class_id}.{attr} to find the callable.
        for attr_pointee in self._ag.get_pointees(id_qualified):
            if attr_pointee in self._id_to_info:
                attr_info = self._id_to_info[attr_pointee]
                if attr_info[0] in (SymbolKind.FUNCTION, SymbolKind.CLASS):
                    return attr_pointee

        return None

    def _classify_unresolved(self, site: _CallSite) -> CallReason:
        """Classify an unresolved call as external or internal.

        For dotted calls (obj.method), checks whether the OBJECT resolves to
        a repo class via the AG. A method name existing somewhere in the repo
        is not sufficient — "close" exists in both repo classes and stdlib.
        """
        callee = site.callee_name

        if "." not in callee:
            return CallReason.UNRESOLVED_INTERNAL if callee in self._symbol_index else CallReason.EXTERNAL

        obj_name, _ = callee.rsplit(".", 1)
        obj_ns = f"{site.caller_ns}.{obj_name}"

        for pointee in self._ag.get_pointees(obj_ns):
            if pointee in self._id_to_info:
                return CallReason.UNRESOLVED_INTERNAL

        return CallReason.EXTERNAL

    def _find_enclosing_symbol(self, namespace: str) -> str | None:
        """Find the symbol ID of the function/method that contains a given namespace."""
        parts = namespace.split(".")

        for i in range(len(parts) - 1, 0, -1):
            if i + 1 < len(parts):
                qualified = f"{parts[i]}.{parts[i + 1]}"
                if qualified in self._symbol_index:
                    return self._symbol_index[qualified]
            if parts[i] in self._symbol_index:
                return self._symbol_index[parts[i]]

        # Module-level call
        for i in range(len(parts), 0, -1):
            candidate_ns = ".".join(parts[:i])
            if candidate_ns in self._module_ns_index:
                return self._module_ns_index[candidate_ns]
        return None
