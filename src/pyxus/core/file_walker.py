"""Repository file discovery for Python source files.

Discovers all .py files in a repository while respecting .gitignore rules
and excluding common non-source directories (virtualenvs, caches, migrations).
Uses ``git ls-files`` when available for accurate .gitignore handling,
falling back to manual directory traversal otherwise.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("pyxus")

# Directories that are always excluded, regardless of .gitignore
DEFAULT_EXCLUDES = frozenset(
    {
        "__pycache__",
        ".pyxus",
        ".git",
        ".venv",
        "venv",
        ".env",
        "node_modules",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".eggs",
    }
)


@dataclass
class SourceFile:
    """A Python source file discovered in the repository.

    Attributes:
        path: Relative path from the repo root (e.g., "services/profiles.py").
        absolute_path: Full filesystem path for reading the file.
        content: The file's source code text, read eagerly during discovery.
    """

    path: str
    absolute_path: str
    content: str


def walk_repository(repo_path: str, exclude_migrations: bool = True) -> list[SourceFile]:
    """Find all Python source files in a repository.

    Strategy:
    1. If the path is inside a git repo, use ``git ls-files`` to get the
       list of tracked .py files (this automatically respects .gitignore).
    2. Otherwise, walk the directory tree manually, skipping DEFAULT_EXCLUDES.

    Args:
        repo_path: Root directory to scan.
        exclude_migrations: If True (default), skip ``migrations/`` directories.

    Returns:
        List of SourceFile objects sorted by relative path.
    """
    repo = Path(repo_path).resolve()
    py_paths = _git_ls_files(repo) or _manual_walk(repo)

    results = []
    for rel_path in sorted(py_paths):
        # Skip excluded directories
        parts = rel_path.parts
        if any(part in DEFAULT_EXCLUDES for part in parts):
            continue
        if exclude_migrations and "migrations" in parts:
            continue

        abs_path = repo / rel_path
        try:
            content = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = abs_path.read_text(encoding="latin-1")
                logger.warning("Non-UTF8 file read with latin-1 fallback: %s", rel_path)
            except (UnicodeDecodeError, OSError):
                logger.warning("Skipping unreadable file: %s", rel_path)
                continue
        except OSError as e:
            logger.warning("Skipping file due to OS error: %s (%s)", rel_path, e)
            continue

        results.append(
            SourceFile(
                path=str(rel_path),
                absolute_path=str(abs_path),
                content=content,
            )
        )

    return results


def _git_ls_files(repo: Path) -> list[Path] | None:
    """Use git to list tracked and untracked (non-gitignored) .py files.

    Returns None if not a git repo or git is unavailable, so the caller
    can fall back to manual walking.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "*.py"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        # -z uses null byte as separator
        paths = [Path(p) for p in result.stdout.split("\0") if p.endswith(".py")]
        return paths
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _manual_walk(repo: Path) -> list[Path]:
    """Walk the directory tree manually when git is not available.

    Skips directories in DEFAULT_EXCLUDES and any directory starting with '.'.
    """
    paths = []
    for py_file in repo.rglob("*.py"):
        rel = py_file.relative_to(repo)
        # Skip hidden directories (other than the repo root)
        if any(part.startswith(".") for part in rel.parts[:-1]):
            continue
        paths.append(rel)
    return paths


def get_modified_files(repo_path: str, since_commit: str | None = None) -> list[str]:
    """Get Python files modified since a given commit or timestamp.

    Used for incremental indexing: only re-analyze files that changed.

    Args:
        repo_path: Root directory of the repository.
        since_commit: Git commit hash to diff against. If None, returns
                      all tracked files (effectively a full re-index).

    Returns:
        List of relative file paths that have been modified.
    """
    if since_commit is None:
        return []

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", since_commit, "HEAD", "--", "*.py"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [p for p in result.stdout.strip().split("\n") if p.endswith(".py")]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
