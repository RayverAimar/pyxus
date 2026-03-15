"""Tests for graph/models.py."""

import pytest

from pyxus.graph.models import (
    RelationKind,
    Relationship,
    Symbol,
    SymbolKind,
    make_relationship_id,
    make_symbol_id,
)


class TestSymbol:
    def test_create_symbol(self):
        s = Symbol(
            id="class:services/profiles.py:ProfileService:1",
            name="ProfileService",
            kind=SymbolKind.CLASS,
            file_path="services/profiles.py",
            start_line=1,
            end_line=50,
        )
        assert s.id == "class:services/profiles.py:ProfileService:1"
        assert s.name == "ProfileService"
        assert s.kind == SymbolKind.CLASS
        assert s.file_path == "services/profiles.py"
        assert s.start_line == 1
        assert s.end_line == 50
        assert s.is_exported is True
        assert s.decorators == ()
        assert s.metadata == {}

    def test_symbol_is_frozen(self):
        s = Symbol(
            id="class:f.py:Foo:1",
            name="Foo",
            kind=SymbolKind.CLASS,
            file_path="f.py",
            start_line=1,
            end_line=10,
        )
        with pytest.raises(AttributeError):
            s.name = "Bar"  # type: ignore[misc]

    def test_symbol_is_hashable(self):
        s = Symbol(
            id="class:f.py:Foo:1",
            name="Foo",
            kind=SymbolKind.CLASS,
            file_path="f.py",
            start_line=1,
            end_line=10,
        )
        assert hash(s) is not None
        assert {s}

    def test_symbol_equality_ignores_metadata(self):
        kwargs = dict(
            id="class:f.py:Foo:1",
            name="Foo",
            kind=SymbolKind.CLASS,
            file_path="f.py",
            start_line=1,
            end_line=10,
        )
        s1 = Symbol(**kwargs, metadata={"django_model": True})
        s2 = Symbol(**kwargs, metadata={})
        assert s1 == s2

    def test_private_symbol_not_exported(self):
        s = Symbol(
            id="function:f.py:_helper:5",
            name="_helper",
            kind=SymbolKind.FUNCTION,
            file_path="f.py",
            start_line=5,
            end_line=10,
            is_exported=False,
        )
        assert s.name == "_helper"
        assert s.kind == SymbolKind.FUNCTION
        assert s.is_exported is False

    def test_symbol_with_decorators(self):
        s = Symbol(
            id="staticmethod:f.py:create:3",
            name="create",
            kind=SymbolKind.STATICMETHOD,
            file_path="f.py",
            start_line=3,
            end_line=20,
            decorators=("staticmethod", "transaction.atomic"),
        )
        assert s.decorators == ("staticmethod", "transaction.atomic")
        assert s.kind == SymbolKind.STATICMETHOD


class TestRelationship:
    def test_create_relationship(self):
        r = Relationship(
            id="calls:a->b",
            source_id="function:f.py:caller:1",
            target_id="function:f.py:callee:10",
            kind=RelationKind.CALLS,
        )
        assert r.id == "calls:a->b"
        assert r.source_id == "function:f.py:caller:1"
        assert r.target_id == "function:f.py:callee:10"
        assert r.kind == RelationKind.CALLS
        assert r.confidence == 1.0
        assert r.metadata == {}

    def test_relationship_is_frozen(self):
        r = Relationship(id="calls:a->b", source_id="a", target_id="b", kind=RelationKind.CALLS)
        with pytest.raises(AttributeError):
            r.kind = RelationKind.IMPORTS  # type: ignore[misc]

    def test_relationship_with_confidence_and_metadata(self):
        r = Relationship(
            id="calls:a->b",
            source_id="a",
            target_id="b",
            kind=RelationKind.CALLS,
            confidence=0.7,
            metadata={"reason": "assignment-graph"},
        )
        assert r.confidence == 0.7
        assert r.metadata == {"reason": "assignment-graph"}


class TestSymbolKind:
    def test_all_kinds_defined(self):
        expected = {"module", "class", "method", "function", "property", "classmethod", "staticmethod"}
        assert {k.value for k in SymbolKind} == expected

    def test_string_value(self):
        assert SymbolKind.CLASS == "class"
        assert SymbolKind.METHOD == "method"


class TestRelationKind:
    def test_core_relations_defined(self):
        core = {"defines", "has_method", "calls", "imports", "extends"}
        assert {k.value for k in RelationKind} == core


class TestMakeSymbolId:
    def test_deterministic(self):
        id1 = make_symbol_id(SymbolKind.CLASS, "f.py", "Foo", 1)
        id2 = make_symbol_id(SymbolKind.CLASS, "f.py", "Foo", 1)
        assert id1 == id2

    def test_format(self):
        sid = make_symbol_id(SymbolKind.CLASS, "services/profiles.py", "ProfileService", 42)
        assert sid == "class:services/profiles.py:ProfileService:42"

    def test_different_inputs_different_ids(self):
        id1 = make_symbol_id(SymbolKind.CLASS, "f.py", "Foo", 1)
        id2 = make_symbol_id(SymbolKind.CLASS, "f.py", "Foo", 2)
        assert id1 != id2


class TestMakeRelationshipId:
    def test_format(self):
        rid = make_relationship_id("class:f.py:A:1", "class:f.py:B:5", RelationKind.EXTENDS)
        assert rid == "extends:class:f.py:A:1->class:f.py:B:5"

    def test_deterministic(self):
        r1 = make_relationship_id("a", "b", RelationKind.CALLS)
        r2 = make_relationship_id("a", "b", RelationKind.CALLS)
        assert r1 == r2

    def test_different_inputs_different_ids(self):
        r1 = make_relationship_id("a", "b", RelationKind.CALLS)
        r2 = make_relationship_id("a", "c", RelationKind.CALLS)
        assert r1 != r2
