"""CLI smoke tests."""

from pathlib import Path

from typer.testing import CliRunner

import j2py.pipeline as pipeline
from j2py.cli.main import app
from j2py.validate.checks import ValidationResult

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_cli_translate_dry_run_without_llm() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "translate",
            str(FIXTURES / "java" / "HelloWorld.java"),
            "--no-llm",
            "--no-validate",
            "--dry-run",
        ],
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

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--no-validate", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Translation order:" in result.output
    assert "1. Base.java" in result.output
    assert "2. Child.java" in result.output


def test_cli_translate_exits_nonzero_on_validation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "Sample.java"
    source.write_text("public class Sample {}")
    output = tmp_path / "Sample.py"

    def fake_validate(source_text: str, path: Path | None = None) -> ValidationResult:
        return ValidationResult(
            path=path or Path("<string>"),
            syntax_ok=True,
            mypy_ok=True,
            ruff_ok=False,
            ruff_errors=["ruff failed"],
        )

    monkeypatch.setattr(pipeline, "validate_source", fake_validate)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["translate", str(source), "--no-llm", "--output", str(output)],
    )

    assert result.exit_code == 1
    assert "Validation issues:" in result.output
    assert "ruff failed" in result.output
