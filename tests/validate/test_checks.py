"""Tests for translated Python validation checks."""

from pathlib import Path

import j2py.validate.checks as checks
from j2py.validate.checks import validate_file, validate_source


def test_validate_source_reports_syntax_error_without_tool_checks(monkeypatch) -> None:
    monkeypatch.setattr(checks, "_run_ruff", lambda path: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(checks, "_run_mypy", lambda path: (_ for _ in ()).throw(AssertionError))

    result = validate_source("def broken(:\n")

    assert not result.ok
    assert not result.syntax_ok
    assert result.syntax_errors
    assert not result.ruff_ok
    assert not result.mypy_ok


def test_validate_source_runs_ruff_and_mypy_for_valid_python(monkeypatch) -> None:
    monkeypatch.setattr(checks, "_run_ruff", lambda path: (True, []))
    monkeypatch.setattr(checks, "_run_mypy", lambda path: (True, []))

    result = validate_source("value: int = 1\n")

    assert result.ok
    assert result.syntax_ok
    assert result.ruff_ok
    assert result.mypy_ok


def test_validate_file_reads_source(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "sample.py"
    path.write_text("value = 1\n")
    monkeypatch.setattr(checks, "_run_ruff", lambda checked: (checked.exists(), []))
    monkeypatch.setattr(checks, "_run_mypy", lambda checked: (checked.exists(), []))

    result = validate_file(path)

    assert result.ok
    assert result.path == path
