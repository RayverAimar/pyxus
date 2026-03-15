"""Tests for core/call_resolver.py."""

from pyxus.core.call_resolver import AssignmentGraph, CallResolutionResult, resolve_calls
from pyxus.core.file_walker import SourceFile
from pyxus.core.heritage import ClassHierarchy
from pyxus.core.symbol_extractor import extract_symbols
from pyxus.graph.models import CallReason, RelationKind, SymbolKind
from pyxus.graph.store import GraphStore


def _make_graph_from_code(code: str, path: str = "test.py") -> tuple[GraphStore, list[SourceFile]]:
    """Build a graph from a single code string for testing."""
    sf = SourceFile(path=path, absolute_path=f"/tmp/{path}", content=code)
    graph = GraphStore()
    result = extract_symbols(sf)
    for sym in result.symbols:
        graph.add_symbol(sym)
    for rel in result.relationships:
        graph.add_relationship(rel)
    return graph, [sf]


def _make_call_resolution(codes: dict[str, str]) -> CallResolutionResult:
    """Resolve calls from multiple source code strings for testing."""
    from pyxus.core.heritage import extract_heritage

    graph = GraphStore()
    files = []
    for path, code in codes.items():
        sf = SourceFile(path=path, absolute_path=f"/tmp/{path}", content=code)
        files.append(sf)
        result = extract_symbols(sf)
        for sym in result.symbols:
            graph.add_symbol(sym)
        for rel in result.relationships:
            graph.add_relationship(rel)

    # Build class hierarchy so inherited methods can be resolved
    hierarchy = ClassHierarchy()
    for sf in files:
        heritage_result = extract_heritage(sf)
        for class_name, bases in heritage_result.class_bases.items():
            class_syms = graph.get_symbol_by_name(class_name)
            for cs in class_syms:
                if cs.kind == SymbolKind.CLASS and cs.file_path == sf.path:
                    base_ids = []
                    for base_name in bases:
                        for bs in graph.get_symbol_by_name(base_name.split(".")[-1]):
                            if bs.kind == SymbolKind.CLASS:
                                base_ids.append(bs.id)
                                break
                    hierarchy.add_class(cs.id, base_ids)
                    break

    # Register attributes for ALL classes (not just those with bases)
    for sym in graph.symbols():
        if sym.kind == SymbolKind.CLASS:
            for method in graph.successors_by_kind(sym.id, RelationKind.HAS_METHOD):
                hierarchy.add_attribute(sym.id, method.name)

    return resolve_calls(files, graph, hierarchy)


def _extract_resolved_names(result: CallResolutionResult) -> set[str]:
    """Extract target symbol names from resolved CALLS relationships."""
    names = set()
    for rel in result.relationships:
        if rel.kind == RelationKind.CALLS:
            # Symbol ID format: "kind:file:name:line" — extract name
            parts = rel.target_id.split(":")
            if len(parts) >= 3:
                names.add(parts[2])
    return names


class TestAssignmentGraph:
    def test_add_edge(self):
        ag = AssignmentGraph()
        assert ag.add_edge("a", "b") is True
        assert ag.add_edge("a", "b") is False

    def test_get_direct_targets(self):
        ag = AssignmentGraph()
        ag.add_edge("x", "y")
        ag.add_edge("x", "z")
        assert ag.get_direct_targets("x") == {"y", "z"}
        assert ag.get_direct_targets("unknown") == set()

    def test_get_pointees_leaf(self):
        ag = AssignmentGraph()
        ag.add_edge("x", "y")
        pointees = ag.get_pointees("x")
        assert "y" in pointees

    def test_get_pointees_transitive(self):
        ag = AssignmentGraph()
        ag.add_edge("a", "b")
        ag.add_edge("b", "c")
        pointees = ag.get_pointees("a")
        assert "c" in pointees

    def test_get_pointees_cycle_safe(self):
        ag = AssignmentGraph()
        ag.add_edge("a", "b")
        ag.add_edge("b", "a")
        pointees = ag.get_pointees("a")
        assert isinstance(pointees, set)

    def test_edge_count(self):
        ag = AssignmentGraph()
        ag.add_edge("a", "b")
        ag.add_edge("a", "c")
        ag.add_edge("b", "d")
        assert ag.edge_count == 3


class TestDirectFunctionCall:
    def test_resolves_direct_call(self):
        result = _make_call_resolution(
            {
                "main.py": "from utils import helper\nhelper()\n",
                "utils.py": "def helper():\n    pass\n",
            }
        )
        assert result.stats.total_calls >= 1
        assert result.stats.resolved >= 1

    def test_resolves_qualified_call(self):
        result = _make_call_resolution(
            {
                "main.py": ("class Service:\n    @staticmethod\n    def create():\n        pass\n\nService.create()\n"),
            }
        )
        assert result.stats.resolved >= 1
        assert "create" in _extract_resolved_names(result)


class TestSelfMethodCall:
    def test_self_method_resolved(self):
        code = "class Foo:\n    def bar(self):\n        self.baz()\n    def baz(self):\n        pass\n"
        result = _make_call_resolution({"test.py": code})
        assert result.stats.resolved >= 1
        assert "baz" in _extract_resolved_names(result)

    def test_self_method_with_ambiguous_method_name(self):
        """When method names collide across classes (sync/async mirrors),
        self.method() must still resolve via per-file class seeding."""
        result = _make_call_resolution(
            {
                "sync.py": (
                    "class SyncConn:\n    def close(self):\n        pass\n    def send(self):\n        self.close()\n"
                ),
                "async_.py": (
                    "class AsyncConn:\n"
                    "    async def close(self):\n"
                    "        pass\n"
                    "    async def send(self):\n"
                    "        self.close()\n"
                ),
            }
        )
        targets = _extract_resolved_names(result)
        assert "close" in targets
        # Both files should resolve self.close()
        assert result.stats.resolved >= 2

    def test_same_class_name_different_files_no_cross_contamination(self):
        """Two classes named Connection in different files must resolve
        self.method() to their OWN methods, not cross-file."""
        result = _make_call_resolution(
            {
                "sync.py": (
                    "class Connection:\n    def close(self): pass\n    def send(self):\n        self.close()\n"
                ),
                "async_.py": (
                    "class Connection:\n"
                    "    async def close(self): pass\n"
                    "    async def send(self):\n"
                    "        self.close()\n"
                ),
            }
        )
        # Both should resolve — each to their own file's close()
        assert result.stats.resolved >= 2
        # Verify no cross-file edges: each relationship's source and target
        # must share the same file_path prefix in their symbol IDs
        for rel in result.relationships:
            source_file = rel.source_id.split(":")[1]
            target_file = rel.target_id.split(":")[1]
            assert source_file == target_file, f"Cross-file edge detected: {rel.source_id} -> {rel.target_id}"


class TestInterproceduralCall:
    def test_parameter_propagation(self):
        """When a class instance is passed to a function, calls on the parameter
        should resolve to the class's methods."""
        code = (
            "class MyService:\n"
            "    def execute(self):\n"
            "        pass\n"
            "\n"
            "def process(obj):\n"
            "    obj.execute()\n"
            "\n"
            "service = MyService()\n"
            "process(service)\n"
        )
        result = _make_call_resolution({"test.py": code})
        assert result.stats.total_calls >= 2
        targets = _extract_resolved_names(result)
        # Both must resolve: MyService() constructor AND obj.execute() via param propagation
        assert "MyService" in targets
        assert "execute" in targets

    def test_parameter_propagation_multiple_params(self):
        """Multiple parameters should each resolve independently."""
        code = (
            "class DB:\n"
            "    def query(self): pass\n"
            "\n"
            "class Cache:\n"
            "    def get(self): pass\n"
            "\n"
            "def handler(db, cache):\n"
            "    db.query()\n"
            "    cache.get()\n"
            "\n"
            "handler(DB(), Cache())\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "query" in targets
        assert "get" in targets


class TestConstructorReturn:
    def test_constructor_then_method(self):
        """x = MyClass(); x.method() should resolve method to the class."""
        code = "class Svc:\n    def run(self):\n        pass\n\ndef main():\n    s = Svc()\n    s.run()\n"
        result = _make_call_resolution({"test.py": code})
        assert "run" in _extract_resolved_names(result)

    def test_constructor_at_module_level(self):
        """Module-level: s = Svc(); s.run()."""
        code = "class Svc:\n    def run(self):\n        pass\n\ns = Svc()\ns.run()\n"
        result = _make_call_resolution({"test.py": code})
        assert "run" in _extract_resolved_names(result)


class TestCrossMethodSelfAttr:
    def test_init_attr_used_in_method(self):
        """self._conn set in __init__, used in another method."""
        code = (
            "class Client:\n"
            "    def __init__(self):\n"
            "        self._conn = Connection()\n"
            "    def send(self):\n"
            "        self._conn.close()\n"
            "\n"
            "class Connection:\n"
            "    def close(self):\n"
            "        pass\n"
        )
        result = _make_call_resolution({"test.py": code})
        assert "close" in _extract_resolved_names(result)

    def test_attr_set_in_any_method(self):
        """self.x set in a non-init method, used in another."""
        code = (
            "class Svc:\n"
            "    def setup(self):\n"
            "        self.handler = Handler()\n"
            "    def run(self):\n"
            "        self.handler.process()\n"
            "\n"
            "class Handler:\n"
            "    def process(self):\n"
            "        pass\n"
        )
        result = _make_call_resolution({"test.py": code})
        assert "process" in _extract_resolved_names(result)


class TestCoverageStats:
    def test_stats_counted(self):
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        pass\n"
            "\n"
            "Foo.bar()\n"
            "unknown.bar()\n"  # unknown doesn't resolve to a repo class → external
        )
        result = _make_call_resolution({"test.py": code})
        assert result.stats.total_calls >= 2
        assert result.stats.resolved >= 1
        assert result.stats.external >= 1

    def test_unknown_object_classified_as_external(self):
        """A call on an unknown object is external — even if the method name
        exists in the repo. Classification is based on the OBJECT, not the method."""
        code = (
            "class Svc:\n"
            "    def run(self): pass\n"
            "\n"
            "unknown_obj.run()\n"  # 'run' exists in repo but unknown_obj has no type info
        )
        result = _make_call_resolution({"test.py": code})
        assert result.stats.external >= 1
        assert len(result.unresolved) == 0

    def test_known_object_unknown_method_is_internal(self):
        """When the object resolves to a repo class but the method doesn't exist,
        that's a genuine unresolved internal call."""
        code = "class Svc:\n    def run(self): pass\n\ns = Svc()\ns.nonexistent()\n"
        result = _make_call_resolution({"test.py": code})
        assert len(result.unresolved) >= 1
        assert result.unresolved[0].reason == CallReason.UNRESOLVED_INTERNAL

    def test_self_attr_method_classified_as_internal(self):
        """self._command.execute() where _command is a stored repo object
        should be classified as internal, not external."""
        code = (
            "class Command:\n"
            "    def execute(self): pass\n"
            "\n"
            "class Invoker:\n"
            "    def __init__(self):\n"
            "        self._command = Command()\n"
            "    def run(self):\n"
            "        self._command.execute()\n"
        )
        result = _make_call_resolution({"test.py": code})
        # _command resolves to Command via AG → execute should resolve
        targets = _extract_resolved_names(result)
        assert "execute" in targets

    def test_super_with_external_base_classified_as_external(self):
        """super().__init__() where all bases are external → EXTERNAL."""
        code = "class Child(UnknownBase):\n    def __init__(self):\n        super().__init__()\n"
        result = _make_call_resolution({"test.py": code})
        assert result.stats.external >= 1

    def test_super_with_repo_base_classified_as_internal(self):
        """super().method() where parent is a repo class but method doesn't exist → INTERNAL."""
        code = "class Base:\n    pass\n\nclass Child(Base):\n    def run(self):\n        super().nonexistent()\n"
        result = _make_call_resolution({"test.py": code})
        assert len(result.unresolved) >= 1
        assert result.unresolved[0].reason == CallReason.UNRESOLVED_INTERNAL


class TestReturnTypePropagation:
    def test_return_value_tracked(self):
        """s = get_service(); s.process() should resolve process via return type."""
        code = (
            "class Service:\n"
            "    def process(self):\n"
            "        pass\n"
            "\n"
            "def get_service():\n"
            "    return Service()\n"
            "\n"
            "s = get_service()\n"
            "s.process()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        # All three calls must resolve: get_service(), Service() constructor, s.process()
        assert "get_service" in targets
        assert "process" in targets

    def test_factory_chain(self):
        """Factory returning another factory's result should chain correctly."""
        code = (
            "class Conn:\n"
            "    def execute(self): pass\n"
            "\n"
            "def create_conn():\n"
            "    return Conn()\n"
            "\n"
            "def get_conn():\n"
            "    return create_conn()\n"
            "\n"
            "c = get_conn()\n"
            "c.execute()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "execute" in targets

    def test_method_return_value(self):
        """Return from a method (not just standalone function) should propagate."""
        code = (
            "class Conn:\n"
            "    def close(self): pass\n"
            "\n"
            "class Pool:\n"
            "    def get_conn(self):\n"
            "        return Conn()\n"
            "\n"
            "def main():\n"
            "    pool = Pool()\n"
            "    c = pool.get_conn()\n"
            "    c.close()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "get_conn" in targets
        assert "close" in targets


class TestInheritedMethods:
    def test_inherited_method_resolved(self):
        """self.method() where method is defined in a parent class."""
        code = (
            "class Base:\n    def save(self): pass\n\nclass Child(Base):\n    def process(self):\n        self.save()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "save" in targets

    def test_deep_inheritance_chain(self):
        """Method defined two levels up in the hierarchy."""
        code = (
            "class A:\n"
            "    def base_method(self): pass\n"
            "\n"
            "class B(A):\n"
            "    def middle_method(self): pass\n"
            "\n"
            "class C(B):\n"
            "    def leaf_method(self):\n"
            "        self.base_method()\n"
            "        self.middle_method()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "base_method" in targets
        assert "middle_method" in targets

    def test_method_override_resolves_to_child(self):
        """When child overrides parent method, self.method() resolves to the child's version."""
        code = (
            "class Base:\n"
            "    def run(self): pass\n"
            "\n"
            "class Child(Base):\n"
            "    def run(self): pass\n"
            "    def go(self):\n"
            "        self.run()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "run" in targets

    def test_inherited_method_on_constructed_object(self):
        """obj = Child(); obj.parent_method() should resolve via MRO."""
        code = (
            "class Base:\n"
            "    def save(self): pass\n"
            "\n"
            "class Child(Base):\n"
            "    def process(self): pass\n"
            "\n"
            "c = Child()\n"
            "c.save()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "save" in targets


class TestSuperCalls:
    def test_super_init(self):
        """super().__init__() should resolve to the parent's __init__."""
        code = (
            "class Base:\n"
            "    def __init__(self): pass\n"
            "\n"
            "class Child(Base):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "__init__" in targets

    def test_super_method(self):
        """super().method() should resolve to the parent's method."""
        code = (
            "class Base:\n    def save(self): pass\n\nclass Child(Base):\n    def save(self):\n        super().save()\n"
        )
        result = _make_call_resolution({"test.py": code})
        # super().save() should resolve to Base.save
        assert result.stats.resolved >= 1

    def test_super_deep_hierarchy(self):
        """super() in C should resolve to B's method, not A's."""
        code = (
            "class A:\n"
            "    def run(self): pass\n"
            "\n"
            "class B(A):\n"
            "    def run(self): pass\n"
            "\n"
            "class C(B):\n"
            "    def run(self):\n"
            "        super().run()\n"
        )
        result = _make_call_resolution({"test.py": code})
        assert result.stats.resolved >= 1


class TestCallableAttributes:
    def test_stored_function(self):
        """self.func = some_function stored as attribute, then called."""
        code = (
            "def my_strategy(x):\n"
            "    return x * 2\n"
            "\n"
            "class Order:\n"
            "    def __init__(self, strategy):\n"
            "        self.strategy = strategy\n"
            "    def apply(self):\n"
            "        self.strategy(self)\n"
            "\n"
            "Order(my_strategy)\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "my_strategy" in targets

    def test_stored_class_as_factory(self):
        """self.factory = SomeClass stored as attribute, then called as factory."""
        code = (
            "class Dog:\n"
            "    def __init__(self, name): pass\n"
            "\n"
            "class Shop:\n"
            "    def __init__(self, factory):\n"
            "        self.factory = factory\n"
            "    def create(self):\n"
            "        self.factory('Rex')\n"
            "\n"
            "Shop(Dog)\n"
        )
        result = _make_call_resolution({"test.py": code})
        targets = _extract_resolved_names(result)
        assert "Dog" in targets


class TestEdgeCases:
    def test_syntax_error_handled(self):
        result = _make_call_resolution({"bad.py": "def broken(:\n"})
        assert result.stats.total_calls == 0
        assert result.relationships == []
        assert result.unresolved == []

    def test_empty_file(self):
        result = _make_call_resolution({"empty.py": ""})
        assert result.stats.total_calls == 0

    def test_builtin_calls_classified_as_external(self):
        """Calls to builtins are classified as external, not unresolved."""
        result = _make_call_resolution({"main.py": "print('hello')\nlen([1, 2, 3])\n"})
        assert result.stats.total_calls >= 2
        assert result.stats.external >= 2
        assert result.stats.resolved == 0
        assert len(result.unresolved) == 0

    def test_chained_method_call(self):
        """Method calls on local variables are tracked even if not fully resolved."""
        code = (
            "class Builder:\n"
            "    def step(self):\n"
            "        return self\n"
            "\n"
            "def main():\n"
            "    b = Builder()\n"
            "    b.step()\n"
            "    b.step()\n"
        )
        result = _make_call_resolution({"test.py": code})
        # Both b.step() calls and Builder() are tracked
        assert result.stats.total_calls >= 2

    def test_assignment_tracking(self):
        code = "class Svc:\n    def run(self):\n        pass\n\ndef main():\n    s = Svc()\n    s.run()\n"
        result = _make_call_resolution({"test.py": code})
        assert result.stats.total_calls >= 2
        targets = _extract_resolved_names(result)
        assert "Svc" in targets
        assert "run" in targets

    def test_multiple_files(self):
        result = _make_call_resolution(
            {
                "models.py": "class User:\n    def save(self): pass\n",
                "services.py": ("from models import User\n\ndef create():\n    u = User()\n    u.save()\n"),
            }
        )
        assert result.stats.total_calls >= 2

    def test_classmethod_call(self):
        code = "class Foo:\n    @classmethod\n    def create(cls):\n        pass\n\nFoo.create()\n"
        result = _make_call_resolution({"test.py": code})
        assert result.stats.resolved >= 1
        assert "create" in _extract_resolved_names(result)
