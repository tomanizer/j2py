"""CLI for post-translation wiring sidecar tooling."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

import typer

from j2py.wire.loader import WiringLoadDiagnostic, load_wiring_sidecars, spring_elements
from j2py.wire.spring_xml import XmlIngestDiagnostic, ingest_spring_xml_files
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
def ingest(
    xml_files: Annotated[
        list[Path],
        typer.Argument(help="Spring XML bean definition file(s) to ingest."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory to write *.wiring.json sidecars."),
    ] = Path("."),
    no_resolve_imports: Annotated[
        bool,
        typer.Option("--no-resolve-imports", help="Do not follow <import resource=...> elements."),
    ] = False,
    output_format: Annotated[
        Literal["text", "json"],
        typer.Option("--format", help="Diagnostic output format."),
    ] = "text",
) -> None:
    """Ingest Spring XML bean definition files and write *.wiring.json sidecars.

    Each XML file produces one sidecar whose elements correspond to <bean>
    definitions. The sidecar uses the same metadata.spring.bean shape as the
    Java @Bean plugin so that downstream validate / generate commands treat
    XML-defined and Java-defined beans uniformly.

    Exit code 0 = success (warnings may be present); 1 = at least one error.
    """
    result = ingest_spring_xml_files(
        xml_files,
        resolve_imports=not no_resolve_imports,
    )

    has_errors = any(d.level == "error" for d in result.diagnostics)
    if has_errors:
        _print_xml_diagnostics(result.diagnostics)
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Detect duplicate output stems before writing so we don't silently
    # overwrite one sidecar with another (e.g. spring/beans.xml vs test/beans.xml).
    stem_counts = Counter(Path(s.source).stem for s in result.sidecars)
    stem_clashes = {stem for stem, count in stem_counts.items() if count > 1}
    if stem_clashes:
        clash_list = ", ".join(sorted(stem_clashes))
        typer.echo(
            f"error: multiple XML files share the same stem ({clash_list}); "
            f"they would overwrite each other in {output_dir}. "
            f"Rename the files or use separate --output directories.",
            err=True,
        )
        raise typer.Exit(code=1)

    written: list[str] = []
    for sidecar in result.sidecars:
        stem = Path(sidecar.source).stem
        sidecar_path = output_dir / f"{stem}.wiring.json"
        sidecar_path.write_text(sidecar.model_dump_json(indent=2), encoding="utf-8")
        written.append(str(sidecar_path))

    if output_format == "json":
        typer.echo(
            json.dumps(
                {
                    "errors": 0,
                    "warnings": sum(1 for d in result.diagnostics if d.level == "warning"),
                    "diagnostics": [
                        {"level": d.level, "path": d.path, "message": d.message}
                        for d in result.diagnostics
                    ],
                    "sidecars_written": written,
                },
                indent=2,
            )
        )
    else:
        _print_xml_diagnostics(result.diagnostics)
        for written_path, sidecar in zip(written, result.sidecars, strict=True):
            typer.echo(f"wrote {written_path} ({len(sidecar.elements)} bean(s))")


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


def _print_xml_diagnostics(diagnostics: list[XmlIngestDiagnostic]) -> None:
    for diagnostic in diagnostics:
        typer.echo(
            f"{diagnostic.level}: {diagnostic.path}: {diagnostic.message}",
            err=diagnostic.level == "error",
        )


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
