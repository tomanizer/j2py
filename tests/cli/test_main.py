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


def test_cli_translate_directory_reports_dependency_order(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Child.java").write_text(
        """
        package com.example;
        import com.example.Base;
        public class Child extends Base {}
        """,
    )
    (source / "Base.java").write_text("package com.example; public class Base {}")
    runner = CliRunner()

    result = runner.invoke(app, ["translate", str(source), "--no-llm", "--dry-run"])

    assert result.exit_code == 0
    assert "Translation order:" in result.output
    assert "1. Base.java" in result.output
    assert "2. Child.java" in result.output
