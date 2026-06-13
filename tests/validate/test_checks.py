"""Tests for translated Python validation checks."""

from pathlib import Path

import j2py.validate.checks as checks
from j2py.validate.checks import validate_directory, validate_file, validate_source


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


def test_validate_directory_runs_tools_once_and_maps_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "out"
    good = output / "com" / "example" / "good.py"
    ruff_bad = output / "com" / "example" / "ruff_bad.py"
    mypy_bad = output / "org" / "example" / "mypy_bad.py"
    calls: list[Path] = []

    def fake_ruff(path: Path) -> tuple[bool, list[str]]:
        calls.append(path)
        return False, [
            f"{path / 'com' / 'example' / 'ruff_bad.py'}:1:1: F821 Undefined name `x`",
        ]

    def fake_mypy(path: Path) -> tuple[bool, list[str]]:
        calls.append(path)
        return False, [
            f"{path / 'org' / 'example' / 'mypy_bad.py'}:1: error: bad type",
        ]

    monkeypatch.setattr(checks, "_run_ruff", fake_ruff)
    monkeypatch.setattr(checks, "_run_mypy", fake_mypy)

    results = validate_directory(
        {
            good: "value: int = 1\n",
            ruff_bad: "x\n",
            mypy_bad: "value: str = 1\n",
        }
    )

    assert len(calls) == 2
    assert results[good].ok
    assert not results[ruff_bad].ok
    assert results[ruff_bad].ruff_errors == [
        f"{ruff_bad}:1:1: F821 Undefined name `x`",
    ]
    assert results[ruff_bad].mypy_ok
    assert not results[mypy_bad].ok
    assert results[mypy_bad].mypy_errors == [
        f"{mypy_bad}:1: error: bad type",
    ]
    assert results[mypy_bad].ruff_ok


def test_validate_directory_never_writes_to_original_absolute_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original = tmp_path / "original" / "absolute.py"

    monkeypatch.setattr(checks, "_run_ruff", lambda path: (True, []))
    monkeypatch.setattr(checks, "_run_mypy", lambda path: (True, []))

    results = validate_directory(
        {
            original: "value: int = 1\n",
            Path("relative.py"): "other: int = 2\n",
        }
    )

    assert results[original].ok
    assert not original.exists()


def test_error_mapping_does_not_match_prefix_paths() -> None:
    original = Path("A.py")
    prefixed = Path("A.py.py")
    temp = Path("/tmp/validate/A.py")
    temp_prefixed = Path("/tmp/validate/A.py.py")

    results = checks._errors_by_original_path(
        [f"{temp_prefixed}:1: error: bad type"],
        {
            temp: original,
            temp_prefixed: prefixed,
        },
    )

    assert results[original] == []
    assert results[prefixed] == [f"{prefixed}:1: error: bad type"]


def test_validate_directory_does_not_run_tools_for_syntax_errors(monkeypatch) -> None:
    monkeypatch.setattr(checks, "_run_ruff", lambda path: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(checks, "_run_mypy", lambda path: (_ for _ in ()).throw(AssertionError))

    result = validate_directory({Path("broken.py"): "def broken(:\n"})[Path("broken.py")]

    assert not result.ok
    assert not result.syntax_ok
    assert result.syntax_errors
