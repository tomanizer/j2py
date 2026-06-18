"""CLI for post-translation wiring sidecar tooling."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from j2py.wire.loader import WiringLoadDiagnostic, load_wiring_sidecars, spring_elements

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
    """Placeholder for target wiring generation."""
    _ = (translated_output_dir, target, output)
    typer.echo("j2py-wire generate is scaffolded; FastAPI generation is tracked by issue #529.")
    raise typer.Exit(code=2)


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
) -> None:
    """Placeholder for target wiring validation."""
    _ = (translated_output_dir, target)
    typer.echo("j2py-wire validate is scaffolded; FastAPI validation is tracked by issue #530.")
    raise typer.Exit(code=2)


def _print_diagnostics(diagnostics: list[WiringLoadDiagnostic]) -> None:
    for diagnostic in diagnostics:
        typer.echo(
            f"{diagnostic.level}: {diagnostic.path}: {diagnostic.message}",
            err=diagnostic.level == "error",
        )


if __name__ == "__main__":
    app()
