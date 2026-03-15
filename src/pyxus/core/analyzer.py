"""Pipeline orchestrator that coordinates all analysis phases.

Runs the full Pyxus analysis pipeline in sequence:
1. Walk repository → discover Python source files
2. Extract symbols → classes, functions, methods from each file
3. Build class hierarchy → inheritance relationships and MRO
4. Resolve imports → map import statements to file paths
5. Resolve calls → PyCG-style assignment graph for call edges
6. Save graph → persist to .pyxus/graph.pkl

Each phase produces data consumed by the next, and the entire pipeline
result is captured in an AnalysisResult for reporting and persistence.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass

from pyxus.core.call_resolver import CallResolutionResult, resolve_calls
from pyxus.core.file_walker import SourceFile, get_modified_files, walk_repository
from pyxus.core.heritage import ClassHierarchy, extract_heritage
from pyxus.core.import_resolver import build_file_index, resolve_imports
from pyxus.core.symbol_extractor import extract_symbols
from pyxus.graph.models import RelationKind, Relationship, SymbolKind, make_relationship_id
from pyxus.graph.persistence import get_index_metadata, load_graph, save_graph
from pyxus.graph.store import GraphStore

logger = logging.getLogger("pyxus")


@dataclass
class AnalysisStats:
    """Summary statistics for a completed analysis run."""

    files_found: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    symbols_extracted: int = 0
    imports_resolved: int = 0
    imports_unresolved: int = 0
    calls_resolved: int = 0
    calls_unresolved: int = 0
    call_resolution_rate: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class AnalysisResult:
    """Complete output of the analysis pipeline."""

    graph: GraphStore
    stats: AnalysisStats
    call_resolution: CallResolutionResult | None = None


def analyze_imports(repo_path: str) -> AnalysisResult:
    """Run a lightweight import-only analysis on a Python repository.

    Skips class hierarchy and call resolution — only builds the module
    dependency graph. Useful for detecting circular imports, understanding
    module coupling, and visualizing project structure.
    """
    start_time = time.monotonic()
    stats = AnalysisStats()
    graph = GraphStore()

    files = _phase_walk(repo_path, stats)
    if not files:
        stats.duration_seconds = time.monotonic() - start_time
        return AnalysisResult(graph=graph, stats=stats)

    indexed_files = _phase_extract(files, graph, stats)
    _phase_imports(indexed_files, graph, stats)

    save_graph(
        graph,
        repo_path,
        extra_metadata={
            "files_indexed": stats.files_indexed,
            "mode": "imports",
        },
    )

    stats.duration_seconds = time.monotonic() - start_time
    logger.info("Import analysis complete in %.1fs", stats.duration_seconds)
    return AnalysisResult(graph=graph, stats=stats)


def analyze(repo_path: str, incremental: bool = False) -> AnalysisResult:
    """Run the full analysis pipeline on a Python repository.

    Args:
        repo_path: Root directory of the repository to analyze.
        incremental: If True, only re-analyze files modified since the
                     last index. Falls back to full analysis if no
                     prior index exists or no commit hash was recorded.
    """
    start_time = time.monotonic()
    stats = AnalysisStats()

    if incremental:
        existing_graph = load_graph(repo_path)
        if existing_graph is not None:
            return _incremental_analyze(repo_path, existing_graph, stats, start_time)
        logger.info("No existing index found — running full analysis")

    return _full_analyze(repo_path, stats, start_time)


def _full_analyze(repo_path: str, stats: AnalysisStats, start_time: float) -> AnalysisResult:
    """Run a complete analysis from scratch."""
    graph = GraphStore()

    files = _phase_walk(repo_path, stats)
    if not files:
        stats.duration_seconds = time.monotonic() - start_time
        return AnalysisResult(graph=graph, stats=stats)

    indexed_files = _phase_extract(files, graph, stats)
    class_hierarchy = _phase_heritage(indexed_files, graph)
    _phase_imports(indexed_files, graph, stats)
    call_result = _phase_calls(indexed_files, graph, class_hierarchy, stats)

    save_graph(
        graph,
        repo_path,
        extra_metadata={
            "files_indexed": stats.files_indexed,
            "call_resolution_rate": round(stats.call_resolution_rate, 3),
            "unresolved_calls": stats.calls_unresolved,
            "last_commit": _get_head_commit(repo_path),
        },
    )

    stats.duration_seconds = time.monotonic() - start_time
    logger.info("Analysis complete in %.1fs", stats.duration_seconds)
    return AnalysisResult(graph=graph, stats=stats, call_resolution=call_result)


# ── Pipeline phases ───────────────────────────────────────────────────────


def _phase_walk(repo_path: str, stats: AnalysisStats) -> list[SourceFile]:
    """Phase 1: Discover Python source files in the repository."""
    logger.info("Scanning files...")
    files = walk_repository(repo_path)
    stats.files_found = len(files)
    logger.info("Found %d Python files", stats.files_found)
    return files


def _phase_extract(files: list[SourceFile], graph: GraphStore, stats: AnalysisStats) -> list[SourceFile]:
    """Phase 2: Extract symbols from each source file."""
    logger.info("Extracting symbols...")
    indexed_files: list[SourceFile] = []

    for source_file in files:
        result = extract_symbols(source_file)
        if not result.symbols:
            stats.files_skipped += 1
            continue

        indexed_files.append(source_file)
        for sym in result.symbols:
            graph.add_symbol(sym)
        for rel in result.relationships:
            graph.add_relationship(rel)

    stats.files_indexed = len(indexed_files)
    stats.symbols_extracted = graph.node_count
    logger.info(
        "Extracted %d symbols from %d files (%d skipped)",
        stats.symbols_extracted,
        stats.files_indexed,
        stats.files_skipped,
    )
    return indexed_files


def _phase_heritage(indexed_files: list[SourceFile], graph: GraphStore) -> ClassHierarchy:
    """Phase 3: Build class hierarchy from inheritance relationships."""
    logger.info("Building class hierarchy...")
    class_hierarchy = ClassHierarchy()

    for source_file in indexed_files:
        heritage_result = extract_heritage(source_file)
        for class_name, bases in heritage_result.class_bases.items():
            class_symbols = graph.get_symbol_by_name(class_name)
            for cs in class_symbols:
                if cs.kind == SymbolKind.CLASS and cs.file_path == source_file.path:
                    base_ids = []
                    for base_name in bases:
                        base_syms = graph.get_symbol_by_name(base_name.split(".")[-1])
                        for bs in base_syms:
                            if bs.kind == SymbolKind.CLASS:
                                base_ids.append(bs.id)
                                graph.add_relationship(
                                    Relationship(
                                        id=make_relationship_id(cs.id, bs.id, RelationKind.EXTENDS),
                                        source_id=cs.id,
                                        target_id=bs.id,
                                        kind=RelationKind.EXTENDS,
                                    )
                                )
                                break
                    class_hierarchy.add_class(cs.id, base_ids)
                    break

    # Register attributes for ALL classes (not just those with bases)
    # so that resolve_attribute can find methods on base classes too
    for sym in graph.symbols():
        if sym.kind == SymbolKind.CLASS:
            for method in graph.successors_by_kind(sym.id, RelationKind.HAS_METHOD):
                class_hierarchy.add_attribute(sym.id, method.name)

    return class_hierarchy


def _phase_imports(indexed_files: list[SourceFile], graph: GraphStore, stats: AnalysisStats) -> None:
    """Phase 4: Resolve import statements to file paths."""
    logger.info("Resolving imports...")
    file_index = build_file_index(indexed_files)
    all_files = {f.path: f for f in indexed_files}

    for source_file in indexed_files:
        import_result = resolve_imports(source_file, file_index, all_files)
        stats.imports_resolved += len(import_result.resolved)
        stats.imports_unresolved += len(import_result.unresolved)
        for rel in import_result.relationships:
            if graph.get_symbol(rel.source_id) and graph.get_symbol(rel.target_id):
                graph.add_relationship(rel)

    logger.info("Resolved %d imports (%d unresolved)", stats.imports_resolved, stats.imports_unresolved)


def _phase_calls(
    indexed_files: list[SourceFile],
    graph: GraphStore,
    class_hierarchy: ClassHierarchy,
    stats: AnalysisStats,
) -> CallResolutionResult:
    """Phase 5: Resolve function/method calls via assignment graph analysis."""
    logger.info("Resolving calls...")
    call_result = resolve_calls(indexed_files, graph, class_hierarchy)

    for rel in call_result.relationships:
        if graph.get_symbol(rel.source_id) and graph.get_symbol(rel.target_id):
            graph.add_relationship(rel)

    stats.calls_resolved = call_result.stats.resolved
    stats.calls_unresolved = call_result.stats.internal_calls - call_result.stats.resolved
    stats.call_resolution_rate = call_result.stats.internal_resolution_rate

    logger.info(
        "Resolved %d / %d intra-repo calls (%.1f%%), %d external",
        stats.calls_resolved,
        call_result.stats.internal_calls,
        stats.call_resolution_rate * 100,
        call_result.stats.external,
    )
    return call_result


# ── Incremental analysis ─────────────────────────────────────────────────


def _incremental_analyze(
    repo_path: str,
    existing_graph: GraphStore,
    stats: AnalysisStats,
    start_time: float,
) -> AnalysisResult:
    """Re-analyze only modified files, updating the existing graph.

    Only re-extracts symbols for changed files. Call and import resolution
    are not re-run — use full analysis for complete resolution.
    """
    metadata = get_index_metadata(repo_path)
    since_commit = metadata.get("last_commit") if metadata else None

    if since_commit is None:
        logger.warning("No last_commit in index metadata — falling back to full analysis")
        return _full_analyze(repo_path, stats, start_time)

    modified = get_modified_files(repo_path, since_commit=since_commit)
    if not modified:
        stats.duration_seconds = time.monotonic() - start_time
        logger.info("No files modified since last index")
        return AnalysisResult(graph=existing_graph, stats=stats)

    logger.info("Re-indexing %d modified files", len(modified))
    logger.warning(
        "Incremental mode: call and import resolution not re-run. "
        "Use `pyxus analyze` (without --incremental) for full resolution."
    )

    for file_path in modified:
        existing_graph.remove_symbols_in_file(file_path)

    files = walk_repository(repo_path)
    modified_files = [f for f in files if f.path in modified]

    for source_file in modified_files:
        result = extract_symbols(source_file)
        for sym in result.symbols:
            existing_graph.add_symbol(sym)
        for rel in result.relationships:
            existing_graph.add_relationship(rel)

    save_graph(existing_graph, repo_path, extra_metadata={"last_commit": _get_head_commit(repo_path)})
    stats.duration_seconds = time.monotonic() - start_time

    return AnalysisResult(graph=existing_graph, stats=stats)


# ── Helpers ───────────────────────────────────────────────────────────────


def _get_head_commit(repo_path: str) -> str | None:
    """Get the current HEAD commit hash for tracking incremental changes."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None
