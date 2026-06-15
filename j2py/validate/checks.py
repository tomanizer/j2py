"""Validation pipeline for translated Python output."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationResult:
    path: Path
    syntax_ok: bool = False
    mypy_ok: bool = False
    ruff_ok: bool = False
    syntax_errors: list[str] = field(default_factory=list)
    mypy_errors: list[str] = field(default_factory=list)
    ruff_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.syntax_ok and self.mypy_ok and self.ruff_ok


def validate_source(source: str, path: Path | None = None) -> ValidationResult:
    """Run all validation checks on Python source text."""
    p = path or Path("<string>")
    result = ValidationResult(path=p)

    # 1. Syntax check (fast, no subprocess)
    try:
        ast.parse(source)
        result.syntax_ok = True
    except SyntaxError as e:
        result.syntax_errors.append(f"SyntaxError: {e}")

    if not result.syntax_ok:
        return result  # no point running further checks

    # 2. Write to a temp file for tool-based checks
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(source)
        tmp = Path(f.name)

    try:
        result.ruff_ok, ruff_errors = _run_ruff(tmp)
        result.mypy_ok, mypy_errors = _run_mypy(tmp)
        result.ruff_errors = [err.replace(str(tmp), str(p)) for err in ruff_errors]
        result.mypy_errors = [err.replace(str(tmp), str(p)) for err in mypy_errors]
    finally:
        tmp.unlink(missing_ok=True)

    return result


def validate_directory(files: dict[Path, str]) -> dict[Path, ValidationResult]:
    """Run validation for many translated Python files with one ruff and one mypy call."""
    results = {
        path: _syntax_validation_result(source, path)
        for path, source in files.items()
    }
    syntax_ok_files = {
        path: source
        for path, source in files.items()
        if results[path].syntax_ok
    }
    if not syntax_ok_files:
        return results

    import tempfile

    relative_paths = _relative_validation_paths(syntax_ok_files.keys())
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_root = Path(tmpdir)
        temp_to_original: dict[Path, Path] = {}
        for original_path, source in syntax_ok_files.items():
            temp_path = temp_root / relative_paths[original_path]
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(source)
            temp_to_original[temp_path] = original_path

        _, ruff_errors = _run_ruff(temp_root)
        _, mypy_errors = _run_mypy(temp_root)

    ruff_by_path = _errors_by_original_path(ruff_errors, temp_to_original)
    mypy_by_path = _errors_by_original_path(mypy_errors, temp_to_original)

    for path in syntax_ok_files:
        result = results[path]
        result.ruff_errors = ruff_by_path.get(path, [])
        result.mypy_errors = mypy_by_path.get(path, [])
        result.ruff_ok = not result.ruff_errors
        result.mypy_ok = not result.mypy_errors

    return results


def validate_file(path: Path) -> ValidationResult:
    return validate_source(path.read_text(), path)


def _syntax_validation_result(source: str, path: Path) -> ValidationResult:
    result = ValidationResult(path=path)
    try:
        ast.parse(source)
        result.syntax_ok = True
    except SyntaxError as e:
        result.syntax_errors.append(f"SyntaxError: {e}")
    return result


def _relative_validation_paths(paths: Iterable[Path]) -> dict[Path, Path]:
    path_list = list(paths)
    if not path_list:
        return {}
    absolute_paths = [
        path if path.is_absolute() else Path.cwd() / path
        for path in path_list
    ]
    common_parent = Path(os.path.commonpath([str(path.parent) for path in absolute_paths]))
    return {
        original_path: absolute_path.relative_to(common_parent)
        for original_path, absolute_path in zip(path_list, absolute_paths, strict=True)
    }


def _errors_by_original_path(
    errors: list[str],
    temp_to_original: dict[Path, Path],
) -> dict[Path, list[str]]:
    by_path: dict[Path, list[str]] = {path: [] for path in temp_to_original.values()}
    for error in errors:
        for temp_path, original_path in temp_to_original.items():
            temp_prefix = str(temp_path)
            if error.startswith(temp_prefix):
                remaining = error[len(temp_prefix):]
                if not remaining or remaining.startswith(":"):
                    by_path[original_path].append(f"{original_path}{remaining}")
                    break
    return by_path


def _run_ruff(path: Path) -> tuple[bool, list[str]]:
    # --select E,F: check real errors (syntax/undefined-name) but skip style/isort rules
    # --isolated: ignore any project ruff.toml so we apply the same rules everywhere
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check",
         "--select", "E,F",
         "--isolated",
         "--output-format=concise",
         str(path)],
        capture_output=True, text=True,
    )
    output = proc.stdout + proc.stderr
    errors = [line for line in output.splitlines() if ": E" in line or ": F" in line]
    return proc.returncode == 0, errors


def _run_mypy(path: Path) -> tuple[bool, list[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--ignore-missing-imports",
         "--no-error-summary", str(path)],
        capture_output=True, text=True,
    )
    errors = [line for line in proc.stdout.splitlines() if ": error:" in line]
    return proc.returncode == 0, errors
