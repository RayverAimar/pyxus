"""Tests for graph/persistence.py."""

import json
from pathlib import Path

import pytest

from pyxus.graph.models import RelationKind, Relationship, Symbol, SymbolKind
from pyxus.graph.persistence import export_json, get_index_metadata, load_graph, save_graph
from pyxus.graph.store import GraphStore


@pytest.fixture
def store_with_data() -> GraphStore:
    """A GraphStore populated with a class and a method for round-trip testing."""
    store = GraphStore()
    cls = Symbol(
        id="class:models.py:User:1",
        name="User",
        kind=SymbolKind.CLASS,
        file_path="models.py",
        start_line=1,
        end_line=20,
    )
    method = Symbol(
        id="method:models.py:save:5",
        name="save",
        kind=SymbolKind.METHOD,
        file_path="models.py",
        start_line=5,
        end_line=15,
    )
    store.add_symbol(cls)
    store.add_symbol(method)
    store.add_relationship(
        Relationship(
            id="has_method:User->save",
            source_id=cls.id,
            target_id=method.id,
            kind=RelationKind.HAS_METHOD,
        )
    )
    return store


class TestSaveAndLoad:
    def test_roundtrip_preserves_graph(self, tmp_path, store_with_data):
        save_graph(store_with_data, str(tmp_path))
        loaded = load_graph(str(tmp_path))

        assert loaded is not None
        assert loaded.node_count == 2
        assert loaded.edge_count == 1
        assert loaded.get_symbol("class:models.py:User:1") is not None
        assert loaded.get_symbol("method:models.py:save:5") is not None

    def test_creates_pyxus_directory(self, tmp_path, store_with_data):
        save_graph(store_with_data, str(tmp_path))
        assert (tmp_path / ".pyxus").is_dir()
        assert (tmp_path / ".pyxus" / "graph.pkl").exists()

    def test_load_nonexistent_returns_none(self, tmp_path):
        assert load_graph(str(tmp_path)) is None

    def test_roundtrip_preserves_traversal(self, tmp_path, store_with_data):
        """Verify that graph traversal still works after save/load."""
        save_graph(store_with_data, str(tmp_path))
        loaded = load_graph(str(tmp_path))

        succs = loaded.successors("class:models.py:User:1")
        assert len(succs) == 1
        assert succs[0][0].name == "save"
        assert succs[0][1].kind == RelationKind.HAS_METHOD

    def test_adds_to_gitignore(self, tmp_path, store_with_data):
        """Ensure .pyxus/ is added to .gitignore if it exists."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n")

        save_graph(store_with_data, str(tmp_path))

        content = gitignore.read_text()
        assert ".pyxus/" in content

    def test_does_not_duplicate_gitignore_entry(self, tmp_path, store_with_data):
        """If .pyxus/ is already in .gitignore, don't add it again."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n.pyxus/\n")

        save_graph(store_with_data, str(tmp_path))

        content = gitignore.read_text()
        assert content.count(".pyxus/") == 1


class TestMetadata:
    def test_metadata_written_on_save(self, tmp_path, store_with_data):
        save_graph(store_with_data, str(tmp_path))
        metadata = get_index_metadata(str(tmp_path))

        assert metadata is not None
        assert metadata["symbol_count"] == 2
        assert metadata["edge_count"] == 1
        assert "indexed_at" in metadata
        assert "pyxus_version" in metadata

    def test_metadata_nonexistent_returns_none(self, tmp_path):
        assert get_index_metadata(str(tmp_path)) is None

    def test_extra_metadata_included(self, tmp_path, store_with_data):
        save_graph(
            store_with_data,
            str(tmp_path),
            extra_metadata={"call_resolution_rate": 0.72, "files_indexed": 10},
        )
        metadata = get_index_metadata(str(tmp_path))
        assert metadata["call_resolution_rate"] == 0.72
        assert metadata["files_indexed"] == 10


class TestJsonExport:
    def test_export_creates_readable_json(self, tmp_path, store_with_data):
        output = str(tmp_path / "graph.json")
        export_json(store_with_data, output)

        data = json.loads(Path(output).read_text())
        assert data["symbol_count"] == 2
        assert data["edge_count"] == 1
        assert len(data["symbols"]) == 2
        assert len(data["relationships"]) == 1

    def test_export_symbol_fields(self, tmp_path, store_with_data):
        output = str(tmp_path / "graph.json")
        export_json(store_with_data, output)

        data = json.loads(Path(output).read_text())
        user_sym = next(s for s in data["symbols"] if s["name"] == "User")
        assert user_sym["kind"] == "class"
        assert user_sym["file_path"] == "models.py"


class TestCorruptedGraph:
    def test_corrupted_pickle_returns_none(self, tmp_path):
        """A corrupted graph.pkl should return None, not crash."""
        pyxus_dir = tmp_path / ".pyxus"
        pyxus_dir.mkdir()
        (pyxus_dir / "graph.pkl").write_bytes(b"corrupted data")

        result = load_graph(str(tmp_path))
        assert result is None

    def test_truncated_pickle_returns_none(self, tmp_path, store_with_data):
        """A truncated graph.pkl should return None."""
        save_graph(store_with_data, str(tmp_path))
        graph_file = tmp_path / ".pyxus" / "graph.pkl"
        # Truncate the file
        data = graph_file.read_bytes()
        graph_file.write_bytes(data[:10])

        result = load_graph(str(tmp_path))
        assert result is None
