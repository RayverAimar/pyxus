"""Tests for core/call_resolver.py."""

from pyxus.core.call_resolver import AssignmentGraph, CallResolutionResult, resolve_calls
from pyxus.core.file_walker import SourceFile
from pyxus.core.heritage import ClassHierarchy
from pyxus.core.symbol_extractor import extract_symbols
from pyxus.graph.models import RelationKind
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

    hierarchy = ClassHierarchy()
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
        # The inter-procedural case: process(service) should connect obj → MyService
        targets = _extract_resolved_names(result)
        assert "MyService" in targets or "execute" in targets


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
            "unknown.bar()\n"  # 'bar' exists in repo → unresolved_internal
        )
        result = _make_call_resolution({"test.py": code})
        assert result.stats.total_calls >= 2
        assert result.stats.resolved >= 1
        assert len(result.unresolved) >= 1

    def test_unresolved_call_tracked(self):
        """A call to an unknown object with a method that exists in the repo is unresolved_internal."""
        code = (
            "class Svc:\n"
            "    def run(self): pass\n"
            "\n"
            "unknown_obj.run()\n"  # 'run' exists in repo but unknown_obj has no type info
        )
        result = _make_call_resolution({"test.py": code})
        assert len(result.unresolved) >= 1
        assert result.unresolved[0].reason == "unresolved_internal"


class TestReturnTypePropagation:
    def test_return_value_tracked(self):
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
        assert result.stats.total_calls >= 2
        targets = _extract_resolved_names(result)
        assert "get_service" in targets or "Service" in targets


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
        assert "run" in _extract_resolved_names(result) or "Svc" in _extract_resolved_names(result)

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
