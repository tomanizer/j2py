"""Validation pipeline for translated Python output."""

from __future__ import annotations

import ast
import subprocess
import sys
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
        result.ruff_ok, result.ruff_errors = _run_ruff(tmp)
        result.mypy_ok, result.mypy_errors = _run_mypy(tmp)
    finally:
        tmp.unlink(missing_ok=True)

    return result


def validate_file(path: Path) -> ValidationResult:
    return validate_source(path.read_text(), path)


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
