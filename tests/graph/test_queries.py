"""Tests for graph/queries.py."""

import pytest

from pyxus.graph.models import RelationKind, Relationship, RiskLevel, Symbol, SymbolKind
from pyxus.graph.queries import context, impact, imports, query
from pyxus.graph.store import GraphStore


@pytest.fixture
def graph_with_service():
    """A graph representing a simple Service class with methods and callers."""
    g = GraphStore()

    # Module
    mod = Symbol(
        id="module:app.py:app.py:0",
        name="app.py",
        kind=SymbolKind.MODULE,
        file_path="app.py",
        start_line=0,
        end_line=0,
    )
    g.add_symbol(mod)

    # Class: Service
    service = Symbol(
        id="class:app.py:Service:1",
        name="Service",
        kind=SymbolKind.CLASS,
        file_path="app.py",
        start_line=1,
        end_line=20,
    )
    g.add_symbol(service)

    # Method: Service.create
    create = Symbol(
        id="staticmethod:app.py:create:3",
        name="create",
        kind=SymbolKind.STATICMETHOD,
        file_path="app.py",
        start_line=3,
        end_line=10,
        decorators=("staticmethod",),
    )
    g.add_symbol(create)

    # Method: Service.update
    update = Symbol(
        id="method:app.py:update:12",
        name="update",
        kind=SymbolKind.METHOD,
        file_path="app.py",
        start_line=12,
        end_line=20,
    )
    g.add_symbol(update)

    # Function: helper
    helper = Symbol(
        id="function:utils.py:helper:1",
        name="helper",
        kind=SymbolKind.FUNCTION,
        file_path="utils.py",
        start_line=1,
        end_line=5,
    )
    g.add_symbol(helper)

    # Function: caller
    caller = Symbol(
        id="function:main.py:caller:1",
        name="caller",
        kind=SymbolKind.FUNCTION,
        file_path="main.py",
        start_line=1,
        end_line=10,
    )
    g.add_symbol(caller)

    # Edges
    g.add_relationship(Relationship(id="r1", source_id=mod.id, target_id=service.id, kind=RelationKind.DEFINES))
    g.add_relationship(Relationship(id="r2", source_id=service.id, target_id=create.id, kind=RelationKind.HAS_METHOD))
    g.add_relationship(Relationship(id="r3", source_id=service.id, target_id=update.id, kind=RelationKind.HAS_METHOD))
    g.add_relationship(Relationship(id="r4", source_id=caller.id, target_id=create.id, kind=RelationKind.CALLS))
    g.add_relationship(Relationship(id="r5", source_id=create.id, target_id=helper.id, kind=RelationKind.CALLS))

    return g


class TestContext:
    def test_returns_class_with_methods(self, graph_with_service):
        result = context(graph_with_service, "Service")
        assert result["symbol"]["name"] == "Service"
        assert result["symbol"]["kind"] == "class"
        assert len(result["methods"]) == 2
        method_names = {m["name"] for m in result["methods"]}
        assert method_names == {"create", "update"}

    def test_returns_function_with_callers(self, graph_with_service):
        result = context(graph_with_service, "create")
        assert result["symbol"]["name"] == "create"
        # Incoming: caller → create (CALLS) and Service → create (HAS_METHOD)
        assert "calls" in result["incoming"]
        assert any(e["name"] == "caller" for e in result["incoming"]["calls"])

    def test_returns_outgoing_calls(self, graph_with_service):
        result = context(graph_with_service, "create")
        assert "calls" in result["outgoing"]
        assert any(e["name"] == "helper" for e in result["outgoing"]["calls"])

    def test_disambiguation_on_multiple_matches(self, graph_with_service):
        """When multiple symbols match, return a candidates list."""
        # Add another 'create' in a different file
        graph_with_service.add_symbol(
            Symbol(
                id="method:other.py:create:5",
                name="create",
                kind=SymbolKind.METHOD,
                file_path="other.py",
                start_line=5,
                end_line=10,
            )
        )
        result = context(graph_with_service, "create")
        assert result.get("disambiguation") is True
        assert len(result["candidates"]) == 2

    def test_not_found(self, graph_with_service):
        result = context(graph_with_service, "nonexistent")
        assert "error" in result


class TestImpact:
    def test_upstream_impact(self, graph_with_service):
        """helper is called by create, which is called by caller."""
        result = impact(graph_with_service, "helper", direction="upstream")
        assert result["target"]["name"] == "helper"
        assert result["direction"] == "upstream"
        # Depth 1: create calls helper
        assert len(result["by_depth"].get("1", [])) >= 1
        assert any(e["name"] == "create" for e in result["by_depth"]["1"])

    def test_downstream_impact(self, graph_with_service):
        """caller calls create, which calls helper."""
        result = impact(graph_with_service, "caller", direction="downstream")
        assert result["target"]["name"] == "caller"
        # Depth 1: caller calls create
        assert any(e["name"] == "create" for e in result["by_depth"].get("1", []))

    def test_risk_levels(self, graph_with_service):
        result = impact(graph_with_service, "helper", direction="upstream")
        assert result["risk"] in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_summary_counts(self, graph_with_service):
        result = impact(graph_with_service, "helper", direction="upstream")
        assert "direct" in result["summary"]
        assert "indirect" in result["summary"]
        assert "total" in result["summary"]
        assert result["summary"]["total"] == result["summary"]["direct"] + result["summary"]["indirect"]

    def test_not_found(self, graph_with_service):
        result = impact(graph_with_service, "nonexistent")
        assert "error" in result

    def test_max_depth_respected(self, graph_with_service):
        result = impact(graph_with_service, "helper", direction="upstream", max_depth=1)
        assert "2" not in result["by_depth"]


class TestQuery:
    def test_exact_match(self, graph_with_service):
        result = query(graph_with_service, "Service")
        assert len(result["results"]) >= 1
        assert result["results"][0]["name"] == "Service"

    def test_prefix_match(self, graph_with_service):
        result = query(graph_with_service, "Serv")
        assert any(r["name"] == "Service" for r in result["results"])

    def test_contains_match(self, graph_with_service):
        result = query(graph_with_service, "help")
        assert any(r["name"] == "helper" for r in result["results"])

    def test_case_insensitive(self, graph_with_service):
        result = query(graph_with_service, "service")
        assert any(r["name"] == "Service" for r in result["results"])

    def test_no_matches(self, graph_with_service):
        result = query(graph_with_service, "zzz_nonexistent")
        assert result["total_matches"] == 0
        assert result["results"] == []

    def test_limit_respected(self, graph_with_service):
        result = query(graph_with_service, "e", limit=2)
        assert len(result["results"]) <= 2

    def test_results_have_score(self, graph_with_service):
        result = query(graph_with_service, "Service")
        assert "score" in result["results"][0]
        assert result["results"][0]["score"] > 0


class TestContextEdgeCases:
    def test_module_only_matches_return_error(self):
        """When all matches are MODULE symbols, context should return error."""
        g = GraphStore()
        g.add_symbol(
            Symbol(
                id="module:test.py:test.py:0",
                name="test.py",
                kind=SymbolKind.MODULE,
                file_path="test.py",
                start_line=0,
                end_line=0,
            )
        )
        result = context(g, "test.py")
        assert "error" in result


class TestImpactEdgeCases:
    def test_disambiguation_on_multiple_matches(self, graph_with_service):
        """Impact should disambiguate when multiple non-MODULE symbols match."""
        graph_with_service.add_symbol(
            Symbol(
                id="method:other.py:create:5",
                name="create",
                kind=SymbolKind.METHOD,
                file_path="other.py",
                start_line=5,
                end_line=10,
            )
        )
        result = impact(graph_with_service, "create")
        assert result.get("disambiguation") is True
        assert len(result["candidates"]) >= 2


class TestImports:
    def test_module_dependencies(self):
        """Import relationships are reported as module dependencies."""
        g = GraphStore()
        mod_a = Symbol(
            id="module:a.py:a.py:0",
            name="a.py",
            kind=SymbolKind.MODULE,
            file_path="a.py",
            start_line=0,
            end_line=0,
        )
        mod_b = Symbol(
            id="module:b.py:b.py:0",
            name="b.py",
            kind=SymbolKind.MODULE,
            file_path="b.py",
            start_line=0,
            end_line=0,
        )
        g.add_symbol(mod_a)
        g.add_symbol(mod_b)
        g.add_relationship(
            Relationship(
                id="r1",
                source_id=mod_a.id,
                target_id=mod_b.id,
                kind=RelationKind.IMPORTS,
            )
        )
        result = imports(g)
        assert result["total_modules"] == 2
        assert result["total_dependencies"] == 1
        assert result["circular_imports"] == []

    def test_circular_import_detected(self):
        """A → B → A is reported as a circular import."""
        g = GraphStore()
        mod_a = Symbol(
            id="module:a.py:a.py:0",
            name="a.py",
            kind=SymbolKind.MODULE,
            file_path="a.py",
            start_line=0,
            end_line=0,
        )
        mod_b = Symbol(
            id="module:b.py:b.py:0",
            name="b.py",
            kind=SymbolKind.MODULE,
            file_path="b.py",
            start_line=0,
            end_line=0,
        )
        g.add_symbol(mod_a)
        g.add_symbol(mod_b)
        g.add_relationship(
            Relationship(
                id="r1",
                source_id=mod_a.id,
                target_id=mod_b.id,
                kind=RelationKind.IMPORTS,
            )
        )
        g.add_relationship(
            Relationship(
                id="r2",
                source_id=mod_b.id,
                target_id=mod_a.id,
                kind=RelationKind.IMPORTS,
            )
        )
        result = imports(g)
        assert len(result["circular_imports"]) >= 1

    def test_no_modules_returns_empty(self):
        g = GraphStore()
        result = imports(g)
        assert result["total_modules"] == 0
        assert result["circular_imports"] == []


class TestRiskThresholds:
    def test_critical_risk(self):
        """More than 10 direct dependents should be CRITICAL."""
        g = GraphStore()
        target = Symbol(
            id="class:a.py:Target:1",
            name="Target",
            kind=SymbolKind.CLASS,
            file_path="a.py",
            start_line=1,
            end_line=5,
        )
        g.add_symbol(target)
        # Add 12 callers
        for i in range(12):
            caller = Symbol(
                id=f"function:a.py:f{i}:{i + 10}",
                name=f"f{i}",
                kind=SymbolKind.FUNCTION,
                file_path="a.py",
                start_line=i + 10,
                end_line=i + 15,
            )
            g.add_symbol(caller)
            g.add_relationship(
                Relationship(
                    id=f"calls:f{i}->Target",
                    source_id=caller.id,
                    target_id=target.id,
                    kind=RelationKind.CALLS,
                )
            )
        result = impact(g, "Target", direction="upstream")
        assert result["risk"] == RiskLevel.CRITICAL

    def test_high_risk(self):
        """6-10 direct dependents should be HIGH."""
        g = GraphStore()
        target = Symbol(
            id="class:a.py:Target:1",
            name="Target",
            kind=SymbolKind.CLASS,
            file_path="a.py",
            start_line=1,
            end_line=5,
        )
        g.add_symbol(target)
        for i in range(7):
            caller = Symbol(
                id=f"function:a.py:f{i}:{i + 10}",
                name=f"f{i}",
                kind=SymbolKind.FUNCTION,
                file_path="a.py",
                start_line=i + 10,
                end_line=i + 15,
            )
            g.add_symbol(caller)
            g.add_relationship(
                Relationship(
                    id=f"calls:f{i}->Target",
                    source_id=caller.id,
                    target_id=target.id,
                    kind=RelationKind.CALLS,
                )
            )
        result = impact(g, "Target", direction="upstream")
        assert result["risk"] == RiskLevel.HIGH

    def test_medium_risk(self):
        """3-5 direct dependents should be MEDIUM."""
        g = GraphStore()
        target = Symbol(
            id="class:a.py:Target:1",
            name="Target",
            kind=SymbolKind.CLASS,
            file_path="a.py",
            start_line=1,
            end_line=5,
        )
        g.add_symbol(target)
        for i in range(4):
            caller = Symbol(
                id=f"function:a.py:f{i}:{i + 10}",
                name=f"f{i}",
                kind=SymbolKind.FUNCTION,
                file_path="a.py",
                start_line=i + 10,
                end_line=i + 15,
            )
            g.add_symbol(caller)
            g.add_relationship(
                Relationship(
                    id=f"calls:f{i}->Target",
                    source_id=caller.id,
                    target_id=target.id,
                    kind=RelationKind.CALLS,
                )
            )
        result = impact(g, "Target", direction="upstream")
        assert result["risk"] == RiskLevel.MEDIUM
