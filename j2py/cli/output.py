"""Shared CLI output helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from j2py.pipeline import PARSE_ERROR_LLM_SKIP_MSG

if TYPE_CHECKING:
    from j2py.pipeline import DirectoryTranslationResult, TranslationResult
    from j2py.validate.checks import ValidationResult
    from j2py.verify.structure import StructuralVerificationResult

console = Console()


def result_payload(result: TranslationResult) -> dict[str, object]:
    validation = result.validation
    structural = result.structural_verification
    diagnostics = result.diagnostics
    return {
        "file": str(result.source_path),
        "output": str(result.output_path) if result.output_path else None,
        "confidence": result.confidence,
        "used_llm": result.used_llm,
        "skipped": result.skipped,
        "parse_ok": result.parse_ok,
        "validation": None
        if validation is None
        else {
            "syntax": validation.syntax_ok,
            "ruff": validation.ruff_ok,
            "mypy": validation.mypy_ok,
            "ok": validation.ok,
            "errors": validation.syntax_errors + validation.ruff_errors + validation.mypy_errors,
        },
        "structural_verification": None
        if structural is None
        else {
            "ok": structural.ok,
            "errors": structural.errors,
        },
        "todos": todo_lines(result.python_source),
        "semantic_warnings": []
        if diagnostics is None
        else [
            {
                "line": item.line,
                "node_type": item.node_type,
                "reason": item.reason,
                "text": item.text,
            }
            for item in diagnostics.warnings
        ],
        "unhandled": []
        if diagnostics is None
        else [
            {
                "line": item.line,
                "node_type": item.node_type,
                "reason": item.reason,
                "text": item.text,
            }
            for item in diagnostics.unhandled
        ],
    }


def directory_payload(batch: DirectoryTranslationResult) -> dict[str, object]:
    return {
        "source_root": str(batch.source_root),
        "output_root": str(batch.output_root),
        "skipped": batch.skipped_count,
        "translated": batch.translated_count,
        "warnings": batch.warnings,
        "files": [result_payload(result) for result in batch.files],
    }


def todo_lines(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if "TODO(j2py)" in line or "__j2py_todo__" in line
    ]


def print_result_summary(result: TranslationResult) -> None:
    diagnostics = result.diagnostics
    handled = len(diagnostics.handled) if diagnostics is not None else 0
    unhandled = len(diagnostics.unhandled) if diagnostics is not None else 0
    warnings = diagnostics.semantic_warning_count if diagnostics is not None else 0
    parse_note = "" if result.parse_ok else ", parse_ok=False"
    console.print(
        f"[dim]{result.source_path.name}: confidence={result.confidence:.2f}, "
        f"handled={handled}, unhandled={unhandled}, warnings={warnings}, "
        f"llm={result.used_llm}{parse_note}[/dim]",
    )
    if not result.parse_ok:
        console.print(f"[yellow]Warning:[/yellow] {PARSE_ERROR_LLM_SKIP_MSG}")
    if result.validation is not None:
        print_validation(result.validation)
    if result.structural_verification is not None:
        print_structural_verification(result.structural_verification)


def print_validation(validation: ValidationResult) -> None:
    skipped = validation.skipped_checks
    if skipped:
        tools = ", ".join(skipped)
        console.print(
            f"[dim]Validation: {tools} not installed — skipped "
            f"(pip install 'j2py-converter[validate]')[/dim]"
        )
    if validation.ok:
        console.print("[green]Validation passed[/green]")
        return
    console.print("[yellow]Validation issues:[/yellow]")
    for err in validation.syntax_errors + validation.mypy_errors + validation.ruff_errors:
        console.print(f"  {err}")


def print_structural_verification(verification: StructuralVerificationResult) -> None:
    if verification.ok:
        console.print("[green]Structural verification passed[/green]")
        return
    console.print("[yellow]Structural verification issues:[/yellow]")
    for err in verification.errors:
        console.print(f"  {err}")


def result_has_blocking_issues(result: TranslationResult, *, validate: bool) -> bool:
    validation_failed = validate and result.validation is not None and not result.validation.ok
    structural_failed = (
        result.structural_verification is not None and not result.structural_verification.ok
    )
    return validation_failed or structural_failed
