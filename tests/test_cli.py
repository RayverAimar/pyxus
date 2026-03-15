"""Tests for cli.py — click CLI commands."""

from pathlib import Path

from click.testing import CliRunner

from pyxus.cli import main
from tests.helpers import make_project


class TestAnalyzeCommand:
    def test_analyze_simple_project(self, tmp_path):
        project = make_project(
            tmp_path,
            {
                "main.py": "class Foo:\n    def bar(self):\n        pass\n",
            },
        )
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", project])
        assert result.exit_code == 0
        assert "Analysis complete" in result.output
        assert "Symbols:" in result.output

    def test_analyze_saves_index(self, tmp_path):
        project = make_project(tmp_path, {"app.py": "x = 1\n"})
        runner = CliRunner()
        runner.invoke(main, ["analyze", project])
        pyxus_dir = Path(project) / ".pyxus"
        assert (pyxus_dir / "graph.pkl").exists()
        assert (pyxus_dir / "metadata.json").exists()

    def test_analyze_quiet_suppresses_output(self, tmp_path):
        project = make_project(tmp_path, {"app.py": "x = 1\n"})
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", project, "--quiet"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_analyze_empty_project(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", str(tmp_path)])
        assert result.exit_code == 0

    def test_analyze_shows_call_resolution(self, tmp_path):
        project = make_project(
            tmp_path,
            {
                "main.py": ("class Svc:\n    def run(self): pass\n\nSvc.run()\n"),
            },
        )
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", project])
        assert result.exit_code == 0
        assert "Call Resolution" in result.output

    def test_analyze_shows_unresolved_calls(self, tmp_path):
        project = make_project(
            tmp_path,
            {
                "main.py": ("class Svc:\n    def run(self): pass\n\nSvc.run()\nunknown_obj.method()\n"),
            },
        )
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", project])
        assert result.exit_code == 0
        assert "Unresolved:" in result.output


class TestStatusCommand:
    def test_status_with_index(self, tmp_path):
        project = make_project(tmp_path, {"app.py": "x = 1\n"})
        runner = CliRunner()
        runner.invoke(main, ["analyze", project])
        result = runner.invoke(main, ["status", project])
        assert result.exit_code == 0
        assert "Symbols:" in result.output
        assert "Indexed at:" in result.output

    def test_status_without_index(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["status", str(tmp_path)])
        assert result.exit_code == 1
        assert "No Pyxus index found" in result.output


class TestCleanCommand:
    def test_clean_removes_pyxus_dir(self, tmp_path):
        project = make_project(tmp_path, {"app.py": "x = 1\n"})
        runner = CliRunner()
        runner.invoke(main, ["analyze", project])
        pyxus_dir = Path(project) / ".pyxus"
        assert pyxus_dir.exists()

        result = runner.invoke(main, ["clean", project])
        assert result.exit_code == 0
        assert not pyxus_dir.exists()
        assert "Removed" in result.output

    def test_clean_no_pyxus_dir(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["clean", str(tmp_path)])
        assert result.exit_code == 0
        assert "No .pyxus/ directory found" in result.output


class TestVersionFlag:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
