"""CLI smoke tests."""

from pathlib import Path

from typer.testing import CliRunner

from j2py.cli.main import app

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_cli_translate_dry_run_without_llm() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(FIXTURES / "java" / "HelloWorld.java"), "--no-llm", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "class HelloWorld:" in result.output
    assert "def get_name" in result.output


def test_cli_analyze_prints_class_inventory() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["analyze", str(FIXTURES / "java" / "HelloWorld.java")])

    assert result.exit_code == 0
    assert "HelloWorld" in result.output
    assert "5 methods" in result.output
    assert "2 fields" in result.output
