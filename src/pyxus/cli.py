"""Command-line interface for Pyxus.

Provides commands to analyze Python codebases, check index status,
manage the .pyxus directory, and start the MCP server.

Usage:
    pyxus analyze [PATH]     Analyze a Python codebase and build the knowledge graph
    pyxus status             Show index status without loading the graph
    pyxus clean              Delete the .pyxus/ directory
    pyxus serve              Start the MCP server (stdio transport)
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import click

from pyxus import __version__


@click.group()
@click.version_option(version=__version__, prog_name="pyxus")
def main() -> None:
    """Pyxus — Python Code Intelligence Engine."""


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--incremental", is_flag=True, help="Only re-analyze modified files.")
@click.option("--quiet", is_flag=True, help="Suppress output (for use in hooks).")
def analyze(path: str, incremental: bool, quiet: bool) -> None:
    """Analyze a Python codebase and build the knowledge graph."""
    log_level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(level=log_level, format="  %(message)s")

    # Deferred: avoids importing the full analysis pipeline on CLI startup
    from pyxus.core.analyzer import analyze as run_analysis

    repo_path = str(Path(path).resolve())

    if not quiet:
        mode = "incremental" if incremental else "full"
        click.echo(f"Pyxus v{__version__} — {mode} analysis of {repo_path}\n")

    result = run_analysis(repo_path, incremental=incremental)
    stats = result.stats

    if quiet:
        return

    # Print summary
    click.echo(f"\n  Analysis complete ({stats.duration_seconds:.1f}s)")
    click.echo(f"  Files: {stats.files_indexed} indexed, {stats.files_skipped} skipped")
    click.echo(f"  Symbols: {stats.symbols_extracted}")
    click.echo(f"  Imports: {stats.imports_resolved} resolved, {stats.imports_unresolved} unresolved")

    if result.call_resolution:
        cr = result.call_resolution
        s = cr.stats
        internal_rate = s.internal_resolution_rate * 100

        click.echo(f"\n  Calls: {s.total_calls} total, {s.external} external (stdlib/third-party)")
        click.echo(f"  Intra-repo resolution: {internal_rate:.1f}% ({s.resolved} / {s.internal_calls})")

        if s.unresolved_by_reason:
            unresolved_internal = s.internal_calls - s.resolved
            click.echo(f"  Unresolved intra-repo: {unresolved_internal}")
            for reason, count in sorted(s.unresolved_by_reason.items(), key=lambda x: -x[1]):
                click.echo(f"    {count:>5} — {reason}")

    click.echo("\n  Saved to .pyxus/")


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def status(path: str) -> None:
    """Show index status: when indexed, symbol count, freshness."""
    # Deferred: only needed for status command
    from pyxus.graph.persistence import get_index_metadata

    repo_path = str(Path(path).resolve())
    metadata = get_index_metadata(repo_path)

    if metadata is None:
        click.echo("No Pyxus index found. Run `pyxus analyze` first.")
        raise SystemExit(1)

    click.echo(f"Pyxus Index Status — {repo_path}\n")
    click.echo(f"  Indexed at:        {metadata.get('indexed_at', 'unknown')}")
    click.echo(f"  Pyxus version:     {metadata.get('pyxus_version', 'unknown')}")
    click.echo(f"  Symbols:           {metadata.get('symbol_count', 0)}")
    click.echo(f"  Edges:             {metadata.get('edge_count', 0)}")

    if "files_indexed" in metadata:
        click.echo(f"  Files indexed:     {metadata['files_indexed']}")
    if "call_resolution_rate" in metadata:
        rate = metadata["call_resolution_rate"] * 100
        click.echo(f"  Call resolution:   {rate:.1f}%")


@main.command(name="imports")
@click.argument("path", default=".", type=click.Path(exists=True))
def imports_cmd(path: str) -> None:
    """Analyze import dependencies and detect circular imports."""
    logging.basicConfig(level=logging.INFO, format="  %(message)s")

    # Deferred: avoids importing the full analysis pipeline on CLI startup
    from pyxus.core.analyzer import analyze_imports
    from pyxus.graph.queries import imports as query_imports

    repo_path = str(Path(path).resolve())
    click.echo(f"Pyxus v{__version__} — import analysis of {repo_path}\n")

    result = analyze_imports(repo_path)
    stats = result.stats

    click.echo(f"  Files: {stats.files_indexed} indexed")
    click.echo(f"  Symbols: {stats.symbols_extracted}")
    click.echo(f"  Imports: {stats.imports_resolved} resolved, {stats.imports_unresolved} unresolved")

    # Run import dependency analysis
    import_data = query_imports(result.graph)

    click.echo(f"\n  Modules: {import_data['total_modules']}")
    click.echo(f"  Dependencies: {import_data['total_dependencies']}")

    cycles = import_data["circular_imports"]
    if cycles:
        click.echo(f"\n  Circular imports detected: {len(cycles)}")
        for cycle in cycles:
            click.echo(f"    {' → '.join(cycle)} → {cycle[0]}")
    else:
        click.echo("\n  No circular imports detected")

    click.echo(f"\n  Analysis complete ({stats.duration_seconds:.1f}s)")


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
def clean(path: str) -> None:
    """Delete the .pyxus/ directory."""
    pyxus_dir = Path(path).resolve() / ".pyxus"
    if pyxus_dir.exists():
        shutil.rmtree(pyxus_dir)
        click.echo(f"Removed {pyxus_dir}")
    else:
        click.echo("No .pyxus/ directory found.")


@main.command()
def serve() -> None:
    """Start the MCP server (stdio transport)."""
    # Deferred: avoids loading FastMCP and graph until serve is invoked
    from pyxus.server import mcp

    mcp.run()
