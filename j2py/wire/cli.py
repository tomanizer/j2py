"""CLI for post-translation wiring sidecar tooling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from j2py.wire.loader import WiringLoadDiagnostic, load_wiring_sidecars, spring_elements
from j2py.wire.targets.fastapi import FastAPITarget
from j2py.wire.validation import (
    ValidationContext,
    ValidationFinding,
    validate_fastapi_wiring,
    validation_exit_code,
)

app = typer.Typer(
    name="j2py-wire",
    help="Inspect and generate framework wiring from j2py sidecars.",
    add_completion=False,
)


@app.command("list")
def list_sidecars(
    translated_output_dir: Annotated[
        Path,
        typer.Argument(help="Translated output directory containing *.wiring.json sidecars."),
    ],
) -> None:
    """List wiring sidecars and element counts."""
    result = load_wiring_sidecars(translated_output_dir)
    _print_diagnostics(result.diagnostics)
    if result.has_errors:
        raise typer.Exit(code=1)

    sidecar_count = len(result.sidecars)
    element_count = sum(len(sidecar.elements) for sidecar in result.sidecars)
    if sidecar_count == 0:
        typer.echo(f"No wiring sidecars found in {translated_output_dir}")
        return

    typer.echo(f"Found {sidecar_count} wiring sidecar(s) with {element_count} element(s).")
    for sidecar in result.sidecars:
        typer.echo(f"{sidecar.output}: {len(sidecar.elements)} element(s)")
    spring_count = len(spring_elements(result.sidecars))
    if spring_count:
        typer.echo(f"Spring metadata elements: {spring_count}")


@app.command()
def generate(
    translated_output_dir: Annotated[
        Path,
        typer.Argument(help="Translated output directory containing *.wiring.json sidecars."),
    ],
    target: Annotated[
        Literal["fastapi"],
        typer.Option("--target", help="Wiring target to generate."),
    ] = "fastapi",
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Generated wiring output directory."),
    ] = Path("wiring"),
) -> None:
    """Generate target wiring from sidecars."""
    result = load_wiring_sidecars(translated_output_dir)
    _print_diagnostics(result.diagnostics)
    if result.has_errors:
        raise typer.Exit(code=1)

    if target == "fastapi":
        generated = FastAPITarget(translated_root=translated_output_dir).generate(
            result.sidecars,
            output,
        )
    else:
        raise typer.Exit(code=2)
    for path in generated:
        typer.echo(f"generated {path}")


@app.command()
def validate(
    translated_output_dir: Annotated[
        Path,
        typer.Argument(help="Translated output directory containing *.wiring.json sidecars."),
    ],
    target: Annotated[
        Literal["fastapi"],
        typer.Option("--target", help="Wiring target to validate."),
    ] = "fastapi",
    wiring_dir: Annotated[
        Path,
        typer.Option("--wiring-dir", help="Generated wiring directory."),
    ] = Path("wiring"),
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Validation output format."),
    ] = "text",
) -> None:
    """Validate generated target wiring."""
    result = load_wiring_sidecars(translated_output_dir)
    _print_diagnostics(result.diagnostics)
    if result.has_errors:
        raise typer.Exit(code=2)

    if target != "fastapi":
        raise typer.Exit(code=2)
    findings = validate_fastapi_wiring(
        ValidationContext(
            translated_root=translated_output_dir,
            wiring_dir=wiring_dir,
            sidecars=result.sidecars,
        ),
    )
    exit_code = validation_exit_code(findings)
    if output_format == "json":
        typer.echo(
            json.dumps(
                {
                    "errors": sum(1 for finding in findings if finding.severity == "error"),
                    "warnings": sum(1 for finding in findings if finding.severity == "warning"),
                    "findings": [finding.to_json() for finding in findings],
                },
                indent=2,
                sort_keys=True,
            ),
        )
    else:
        _print_validation_summary(findings)
    raise typer.Exit(code=exit_code)


def _print_diagnostics(diagnostics: list[WiringLoadDiagnostic]) -> None:
    for diagnostic in diagnostics:
        typer.echo(
            f"{diagnostic.level}: {diagnostic.path}: {diagnostic.message}",
            err=diagnostic.level == "error",
        )


def _print_validation_summary(findings: list[ValidationFinding]) -> None:
    errors = sum(1 for finding in findings if finding.severity == "error")
    warnings = sum(1 for finding in findings if finding.severity == "warning")
    typer.echo(f"j2py-wire validate - {len(findings)} issues found")
    typer.echo("")
    for finding in findings:
        location = finding.path + (f":{finding.line}" if finding.line is not None else "")
        typer.echo(f"{finding.severity.upper()}  {location}")
        typer.echo(f"  {finding.message}")
        typer.echo(f"  Fix: {finding.fix}")
        typer.echo("")
    typer.echo(f"{errors} errors, {warnings} warnings")


if __name__ == "__main__":
    app()
