"""Tests for graph/store.py."""

import pytest

from pyxus.graph.models import RelationKind, Relationship, Symbol, SymbolKind
from pyxus.graph.store import GraphStore


def _make_store() -> GraphStore:
    return GraphStore()


def _make_class_symbol() -> Symbol:
    return Symbol(
        id="class:f.py:Foo:1",
        name="Foo",
        kind=SymbolKind.CLASS,
        file_path="f.py",
        start_line=1,
        end_line=20,
    )


def _make_method_symbol() -> Symbol:
    return Symbol(
        id="method:f.py:bar:3",
        name="bar",
        kind=SymbolKind.METHOD,
        file_path="f.py",
        start_line=3,
        end_line=10,
    )


def _make_function_symbol() -> Symbol:
    return Symbol(
        id="function:g.py:helper:1",
        name="helper",
        kind=SymbolKind.FUNCTION,
        file_path="g.py",
        start_line=1,
        end_line=5,
    )


class TestAddAndGetSymbol:
    def test_add_and_get(self):
        store = _make_store()
        sym = _make_class_symbol()
        store.add_symbol(sym)
        assert store.get_symbol(sym.id) == sym

    def test_get_nonexistent_returns_none(self):
        store = _make_store()
        assert store.get_symbol("nonexistent") is None

    def test_duplicate_is_idempotent(self):
        store = _make_store()
        sym = _make_class_symbol()
        idx1 = store.add_symbol(sym)
        idx2 = store.add_symbol(sym)
        assert idx1 == idx2
        assert store.node_count == 1


class TestAddRelationship:
    def test_add_edge(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        rel = Relationship(
            id="has_method:Foo->bar",
            source_id=cls.id,
            target_id=method.id,
            kind=RelationKind.HAS_METHOD,
        )
        store.add_relationship(rel)
        assert store.edge_count == 1

    def test_missing_source_raises(self):
        store = _make_store()
        method = _make_method_symbol()
        store.add_symbol(method)
        rel = Relationship(
            id="calls:x->y",
            source_id="nonexistent",
            target_id=method.id,
            kind=RelationKind.CALLS,
        )
        with pytest.raises(KeyError, match="Source symbol not found"):
            store.add_relationship(rel)

    def test_missing_target_raises(self):
        store = _make_store()
        cls = _make_class_symbol()
        store.add_symbol(cls)
        rel = Relationship(
            id="calls:x->y",
            source_id=cls.id,
            target_id="nonexistent",
            kind=RelationKind.CALLS,
        )
        with pytest.raises(KeyError, match="Target symbol not found"):
            store.add_relationship(rel)


class TestPredecessorsAndSuccessors:
    def test_successors(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        store.add_relationship(
            Relationship(
                id="has_method:Foo->bar",
                source_id=cls.id,
                target_id=method.id,
                kind=RelationKind.HAS_METHOD,
            )
        )

        succs = store.successors(cls.id)
        assert len(succs) == 1
        assert succs[0][0] == method
        assert succs[0][1].kind == RelationKind.HAS_METHOD

    def test_predecessors(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        store.add_relationship(
            Relationship(
                id="has_method:Foo->bar",
                source_id=cls.id,
                target_id=method.id,
                kind=RelationKind.HAS_METHOD,
            )
        )

        preds = store.predecessors(method.id)
        assert len(preds) == 1
        assert preds[0][0] == cls
        assert preds[0][1].kind == RelationKind.HAS_METHOD

    def test_no_edges_returns_empty(self):
        store = _make_store()
        cls = _make_class_symbol()
        store.add_symbol(cls)
        assert store.successors(cls.id) == []
        assert store.predecessors(cls.id) == []

    def test_nonexistent_symbol_returns_empty(self):
        store = _make_store()
        assert store.successors("nonexistent") == []
        assert store.predecessors("nonexistent") == []


class TestFilterByKind:
    def test_successors_by_kind(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        func = _make_function_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        store.add_symbol(func)
        store.add_relationship(
            Relationship(
                id="has_method:Foo->bar",
                source_id=cls.id,
                target_id=method.id,
                kind=RelationKind.HAS_METHOD,
            )
        )
        store.add_relationship(
            Relationship(
                id="calls:Foo->helper",
                source_id=cls.id,
                target_id=func.id,
                kind=RelationKind.CALLS,
            )
        )

        methods = store.successors_by_kind(cls.id, RelationKind.HAS_METHOD)
        assert len(methods) == 1
        assert methods[0] == method

        calls = store.successors_by_kind(cls.id, RelationKind.CALLS)
        assert len(calls) == 1
        assert calls[0] == func

    def test_predecessors_by_kind(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        store.add_relationship(
            Relationship(
                id="has_method:Foo->bar",
                source_id=cls.id,
                target_id=method.id,
                kind=RelationKind.HAS_METHOD,
            )
        )
        assert store.predecessors_by_kind(method.id, RelationKind.HAS_METHOD) == [cls]
        assert store.predecessors_by_kind(method.id, RelationKind.CALLS) == []


class TestLookups:
    def test_get_symbol_by_name(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        assert store.get_symbol_by_name("Foo") == [cls]
        assert store.get_symbol_by_name("nonexistent") == []

    def test_get_symbols_in_file(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        func = _make_function_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        store.add_symbol(func)
        f_symbols = store.get_symbols_in_file("f.py")
        assert len(f_symbols) == 2
        assert cls in f_symbols
        assert method in f_symbols


class TestStats:
    def test_counts(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        assert store.node_count == 0
        assert store.edge_count == 0
        store.add_symbol(cls)
        store.add_symbol(method)
        assert store.node_count == 2
        store.add_relationship(
            Relationship(
                id="has_method:Foo->bar",
                source_id=cls.id,
                target_id=method.id,
                kind=RelationKind.HAS_METHOD,
            )
        )
        assert store.edge_count == 1

    def test_symbols_list(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        assert len(store.symbols()) == 2

    def test_relationships_list(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        store.add_relationship(
            Relationship(
                id="has_method:Foo->bar",
                source_id=cls.id,
                target_id=method.id,
                kind=RelationKind.HAS_METHOD,
            )
        )
        rels = store.relationships()
        assert len(rels) == 1
        assert rels[0].kind == RelationKind.HAS_METHOD


class TestRemoveSymbolsInFile:
    def test_remove(self):
        store = _make_store()
        cls = _make_class_symbol()
        method = _make_method_symbol()
        func = _make_function_symbol()
        store.add_symbol(cls)
        store.add_symbol(method)
        store.add_symbol(func)
        removed = store.remove_symbols_in_file("f.py")
        assert removed == 2
        assert store.node_count == 1
        assert store.get_symbol(cls.id) is None
        assert store.get_symbol(func.id) is not None
