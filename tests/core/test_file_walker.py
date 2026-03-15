"""Tests for core/file_walker.py."""

from pathlib import Path

from pyxus.core.file_walker import walk_repository


def _make_py_file(path: Path, content: str = "x = 1\n") -> None:
    """Create a .py file with parent directories for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestWalkRepository:
    def test_finds_py_files(self, tmp_path):
        _make_py_file(tmp_path / "main.py")
        _make_py_file(tmp_path / "utils.py")
        _make_py_file(tmp_path / "sub" / "helpers.py")

        files = walk_repository(str(tmp_path))
        paths = {f.path for f in files}

        assert "main.py" in paths
        assert "utils.py" in paths
        assert str(Path("sub") / "helpers.py") in paths

    def test_reads_file_content(self, tmp_path):
        _make_py_file(tmp_path / "main.py", "print('hello')\n")

        files = walk_repository(str(tmp_path))
        assert len(files) == 1
        assert files[0].content == "print('hello')\n"

    def test_excludes_venv(self, tmp_path):
        _make_py_file(tmp_path / "main.py")
        _make_py_file(tmp_path / ".venv" / "lib" / "site.py")
        _make_py_file(tmp_path / "venv" / "lib" / "site.py")

        files = walk_repository(str(tmp_path))
        paths = {f.path for f in files}

        assert "main.py" in paths
        assert not any(".venv" in p for p in paths)
        assert not any("venv" in p for p in paths)

    def test_excludes_pycache(self, tmp_path):
        _make_py_file(tmp_path / "main.py")
        _make_py_file(tmp_path / "__pycache__" / "main.cpython-312.pyc")

        files = walk_repository(str(tmp_path))
        assert all("__pycache__" not in f.path for f in files)

    def test_excludes_migrations_by_default(self, tmp_path):
        _make_py_file(tmp_path / "app.py")
        _make_py_file(tmp_path / "migrations" / "0001_initial.py")

        files = walk_repository(str(tmp_path))
        assert all("migrations" not in f.path for f in files)

    def test_includes_migrations_when_requested(self, tmp_path):
        _make_py_file(tmp_path / "app.py")
        _make_py_file(tmp_path / "migrations" / "0001_initial.py")

        files = walk_repository(str(tmp_path), exclude_migrations=False)
        paths = {f.path for f in files}
        assert str(Path("migrations") / "0001_initial.py") in paths

    def test_excludes_pyxus_dir(self, tmp_path):
        _make_py_file(tmp_path / "main.py")
        _make_py_file(tmp_path / ".pyxus" / "internal.py")

        files = walk_repository(str(tmp_path))
        assert all(".pyxus" not in f.path for f in files)

    def test_sorted_by_path(self, tmp_path):
        _make_py_file(tmp_path / "z.py")
        _make_py_file(tmp_path / "a.py")
        _make_py_file(tmp_path / "m.py")

        files = walk_repository(str(tmp_path))
        paths = [f.path for f in files]
        assert paths == sorted(paths)

    def test_empty_directory(self, tmp_path):
        files = walk_repository(str(tmp_path))
        assert files == []

    def test_ignores_non_py_files(self, tmp_path):
        _make_py_file(tmp_path / "main.py")
        (tmp_path / "readme.md").write_text("# readme")
        (tmp_path / "config.yaml").write_text("key: value")

        files = walk_repository(str(tmp_path))
        assert len(files) == 1
        assert files[0].path == "main.py"

    def test_absolute_path_is_set(self, tmp_path):
        _make_py_file(tmp_path / "main.py")

        files = walk_repository(str(tmp_path))
        assert files[0].absolute_path == str((tmp_path / "main.py").resolve())

    def test_handles_latin1_encoding(self, tmp_path):
        """Files with non-UTF8 encoding should be read with fallback."""
        path = tmp_path / "latin.py"
        path.write_bytes(b"# caf\xe9\nx = 1\n")

        files = walk_repository(str(tmp_path))
        assert len(files) == 1
        assert "x = 1" in files[0].content

    def test_excludes_hidden_directories(self, tmp_path):
        _make_py_file(tmp_path / "main.py")
        _make_py_file(tmp_path / ".hidden" / "secret.py")

        files = walk_repository(str(tmp_path))
        assert all(".hidden" not in f.path for f in files)

    def test_excludes_build_directories(self, tmp_path):
        _make_py_file(tmp_path / "main.py")
        _make_py_file(tmp_path / "dist" / "pkg.py")
        _make_py_file(tmp_path / "build" / "lib.py")

        files = walk_repository(str(tmp_path))
        assert all("dist" not in f.path for f in files)
        assert all("build" not in f.path for f in files)


class TestGetModifiedFiles:
    def test_no_commit_returns_empty(self, tmp_path):
        from pyxus.core.file_walker import get_modified_files

        result = get_modified_files(str(tmp_path), since_commit=None)
        assert result == []

    def test_invalid_repo_returns_empty(self, tmp_path):
        from pyxus.core.file_walker import get_modified_files

        result = get_modified_files(str(tmp_path), since_commit="abc123")
        assert result == []
