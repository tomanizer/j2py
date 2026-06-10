"""j2py CLI — Java to Python converter."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="j2py",
    help="Convert Java source files to Python.",
    add_completion=False,
)
console = Console()


@app.command()
def translate(
    source: Path = typer.Argument(..., help="Java file or directory to translate."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file or directory."),
    config: list[Path] = typer.Option([], "--config", "-c", help="Extra config file(s) to layer on top of defaults."),
    llm: bool = typer.Option(True, "--llm/--no-llm", help="Use LLM for complex logic (requires ANTHROPIC_API_KEY)."),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="Claude model to use."),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run mypy + ruff on output."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print translated output, do not write files."),
) -> None:
    """Translate a Java file or directory tree to Python."""
    from j2py.config.loader import ConfigLoader
    from j2py.pipeline import translate_file, translate_directory

    loader = ConfigLoader().add_defaults()
    for c in config:
        loader.add_file(c)
    cfg = loader.build()

    if source.is_dir():
        _translate_dir(source, output or source.parent / (source.name + "_py"),
                       cfg, llm, model, validate, dry_run)
    else:
        _translate_single(source, output, cfg, llm, model, validate, dry_run)


def _translate_single(
    source: Path,
    output: Path | None,
    cfg,
    llm: bool,
    model: str,
    validate: bool,
    dry_run: bool,
) -> None:
    from j2py.pipeline import translate_file

    console.print(f"[bold]Translating[/bold] {source}")
    result = translate_file(source, cfg=cfg, use_llm=llm, model=model)

    if dry_run:
        console.print(result.python_source)
        return

    dest = output or source.with_suffix(".py")
    dest.write_text(result.python_source)
    console.print(f"[green]Written:[/green] {dest}")

    if validate:
        from j2py.validate.checks import validate_file
        vr = validate_file(dest)
        if vr.ok:
            console.print("[green]Validation passed[/green]")
        else:
            console.print("[yellow]Validation issues:[/yellow]")
            for err in vr.syntax_errors + vr.mypy_errors + vr.ruff_errors:
                console.print(f"  {err}")


def _translate_dir(
    source: Path,
    output: Path,
    cfg,
    llm: bool,
    model: str,
    validate: bool,
    dry_run: bool,
) -> None:
    from j2py.pipeline import translate_file

    java_files = sorted(source.rglob("*.java"))
    if not java_files:
        console.print("[yellow]No .java files found.[/yellow]")
        return

    output.mkdir(parents=True, exist_ok=True)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Translating...", total=len(java_files))
        for jf in java_files:
            progress.update(task, description=f"[cyan]{jf.name}[/cyan]")
            result = translate_file(jf, cfg=cfg, use_llm=llm, model=model)
            rel = jf.relative_to(source).with_suffix(".py")
            dest = output / rel
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(result.python_source)
            progress.advance(task)

    console.print(f"[green]Done.[/green] {len(java_files)} files → {output}")


@app.command()
def analyze(
    source: Path = typer.Argument(..., help="Java file or directory to analyze."),
) -> None:
    """Print dependency graph and class inventory without translating."""
    from j2py.parse.java_ast import parse_file
    from j2py.analyze.symbols import extract_symbols

    java_files = list(source.rglob("*.java")) if source.is_dir() else [source]
    for jf in java_files:
        parsed = parse_file(jf)
        symbols = extract_symbols(parsed)
        console.print(f"\n[bold]{jf}[/bold] — package: {symbols.package}")
        for cls in symbols.classes:
            kind = "interface" if cls.is_interface else ("enum" if cls.is_enum else "class")
            console.print(f"  [{kind}] {cls.name} — {len(cls.methods)} methods, {len(cls.fields)} fields")


if __name__ == "__main__":
    app()
