"""Shared test helpers used across multiple test modules.

Convention: all helpers use the ``_make_`` prefix to create test data.
"""

from __future__ import annotations

from pathlib import Path

from pyxus.core.file_walker import SourceFile


def make_source_file(path: str = "test.py", content: str = "", absolute_prefix: str = "/tmp") -> SourceFile:
    """Create a SourceFile for testing without touching the filesystem."""
    return SourceFile(path=path, absolute_path=f"{absolute_prefix}/{path}", content=content)


def make_project(tmp_path: Path, files: dict[str, str]) -> str:
    """Create a temporary Python project directory with the given files.

    Returns the project root path as a string (for passing to analyze()).
    """
    for rel_path, content in files.items():
        full_path = tmp_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
    return str(tmp_path)
