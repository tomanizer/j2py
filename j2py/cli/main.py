"""j2py CLI — Java to Python converter."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

if TYPE_CHECKING:
    from j2py.config.loader import TranslationConfig
    from j2py.pipeline import TranslationResult
    from j2py.validate.checks import ValidationResult

app = typer.Typer(
    name="j2py",
    help="Convert Java source files to Python.",
    add_completion=False,
)
console = Console()


@app.command()
def translate(
    source: Path = typer.Argument(..., help="Java file or directory to translate."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file or directory."),
    config: list[Path] = typer.Option(
        [], "--config", "-c", help="Extra config file(s) to layer on top of defaults."
    ),
    llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use LLM completion for unresolved logic (requires the configured LLM API key).",
    ),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model ID to use."),
    validate: bool = typer.Option(
        True, "--validate/--no-validate", help="Run mypy + ruff on output."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print translated output, do not write files."
    ),
) -> None:
    """Translate a Java file or directory tree to Python."""
    cfg = _load_config(config)

    if source.is_dir():
        _translate_dir(source, output or source.parent / (source.name + "_py"),
                       cfg, llm, model, validate, dry_run)
    else:
        _translate_single(source, output, cfg, llm, model, validate, dry_run)


def _translate_single(
    source: Path,
    output: Path | None,
    cfg: TranslationConfig,
    llm: bool,
    model: str,
    validate: bool,
    dry_run: bool,
) -> None:
    from j2py.pipeline import translate_file

    console.print(f"[bold]Translating[/bold] {source}")
    result = translate_file(source, cfg=cfg, use_llm=llm, model=model, validate=validate)
    _print_result_summary(result)

    if dry_run:
        console.print(result.python_source)
        if validate and result.validation is not None and not result.validation.ok:
            raise typer.Exit(code=1)
        return

    dest = output or source.with_suffix(".py")
    dest.write_text(result.python_source)
    console.print(f"[green]Written:[/green] {dest}")
    _emit_runtime_module(dest.parent, [result.python_source])

    if validate and result.validation is not None:
        _print_validation(result.validation)
        if not result.validation.ok:
            raise typer.Exit(code=1)


def _emit_runtime_module(output_root: Path, sources: list[str]) -> None:
    """Vendor j2py_runtime.py next to translated output when dispatch is used."""
    from j2py.translate.runtime import (
        RUNTIME_IMPORT_LINE,
        RUNTIME_MODULE_NAME,
        runtime_module_source,
    )

    if not any(RUNTIME_IMPORT_LINE in source for source in sources):
        return
    runtime_path = output_root / f"{RUNTIME_MODULE_NAME}.py"
    runtime_path.write_text(runtime_module_source())
    console.print(f"[green]Written:[/green] {runtime_path} (overload dispatch runtime)")


def _translate_dir(
    source: Path,
    output: Path,
    cfg: TranslationConfig,
    llm: bool,
    model: str,
    validate: bool,
    dry_run: bool,
) -> None:
    from j2py.pipeline import translate_directory

    java_files = sorted(source.rglob("*.java"))
    if not java_files:
        console.print("[yellow]No .java files found.[/yellow]")
        return

    batch = translate_directory(
        source,
        output,
        cfg=cfg,
        use_llm=llm,
        model=model,
        validate=validate,
    )
    console.print("[bold]Translation order:[/bold]")
    for index, path in enumerate(batch.order, start=1):
        console.print(f"  {index}. {path.relative_to(source)}")
    for warning in batch.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")

    if not dry_run:
        output.mkdir(parents=True, exist_ok=True)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Writing...", total=len(batch.files))
        for result in batch.files:
            progress.update(task, description=f"[cyan]{result.source_path.name}[/cyan]")
            _print_result_summary(result)
            if dry_run:
                console.print(f"\n[bold]{result.source_path}[/bold]")
                console.print(result.python_source)
            elif result.output_path is not None:
                result.output_path.parent.mkdir(parents=True, exist_ok=True)
                result.output_path.write_text(result.python_source)
            progress.advance(task)

    if not dry_run:
        _emit_runtime_module(output, [result.python_source for result in batch.files])

    console.print(f"[green]Done.[/green] {len(batch.files)} files → {output}")
    failures = [
        result
        for result in batch.files
        if result.validation is not None and not result.validation.ok
    ]
    if failures:
        console.print("[yellow]Validation failures:[/yellow]")
        for result in failures:
            console.print(f"  {result.source_path}")
            if result.validation is not None:
                _print_validation(result.validation)
        raise typer.Exit(code=1)


@app.command()
def analyze(
    source: Path = typer.Argument(..., help="Java file or directory to analyze."),
) -> None:
    """Print dependency graph and class inventory without translating."""
    from j2py.analyze.symbols import extract_symbols
    from j2py.parse.java_ast import parse_file

    java_files = list(source.rglob("*.java")) if source.is_dir() else [source]
    for jf in java_files:
        parsed = parse_file(jf)
        symbols = extract_symbols(parsed)
        console.print(f"\n[bold]{jf}[/bold] — package: {symbols.package}")
        for cls in symbols.classes:
            kind = "interface" if cls.is_interface else ("enum" if cls.is_enum else "class")
            console.print(
                f"  [{kind}] {cls.name} — {len(cls.methods)} methods, {len(cls.fields)} fields"
            )


@app.command()
def compare(
    source: Path = typer.Argument(..., help="Java source file to compare."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Python file. If it exists, translation is skipped.",
    ),
    config: list[Path] = typer.Option(
        [], "--config", "-c", help="Extra config file(s) to layer on top of defaults."
    ),
    llm: bool = typer.Option(
        False,
        "--llm/--no-llm",
        help="Use LLM when translating (default: off for speed).",
    ),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m", help="LLM model ID to use."),
    editor: str = typer.Option(
        "code",
        "--editor",
        help="Editor binary for the diff (for example: cursor, code-insiders).",
    ),
    no_open: bool = typer.Option(
        False,
        "--no-open",
        help="Print file paths only; do not open editor.",
    ),
) -> None:
    """Open a side-by-side diff of a Java source file and its Python translation."""
    if not source.exists():
        console.print(f"[red]Error:[/red] source file not found: {source}")
        raise typer.Exit(code=1)
    if not source.is_file():
        console.print("[red]Error:[/red] compare only supports single files, not directories.")
        raise typer.Exit(code=1)

    py_path = _resolve_py_path(source, output)
    if py_path.exists() and py_path.is_dir():
        console.print(f"[red]Error:[/red] Python output path is a directory: {py_path}")
        raise typer.Exit(code=1)

    if py_path.exists():
        console.print(f"[dim]Skipping translation — using existing file:[/dim] {py_path}")
    else:
        from j2py.pipeline import translate_file

        cfg = _load_config(config)
        console.print(f"[bold]Translating[/bold] {source}")
        result = translate_file(source, cfg=cfg, use_llm=llm, model=model, validate=False)
        _print_result_summary(result)
        py_path.parent.mkdir(parents=True, exist_ok=True)
        py_path.write_text(result.python_source)
        console.print(f"[green]Written:[/green] {py_path}")
        _emit_runtime_module(py_path.parent, [result.python_source])

    if no_open:
        console.print(f"Java:   {source}", soft_wrap=True)
        console.print(f"Python: {py_path}", soft_wrap=True)
        console.print(f"Diff:   {editor} --diff {source} {py_path}", soft_wrap=True)
        return

    _open_diff(source, py_path, editor)


def _resolve_py_path(source: Path, output: Path | None) -> Path:
    return output if output is not None else source.with_suffix(".py")


def _open_diff(source: Path, py_path: Path, editor: str) -> None:
    try:
        subprocess.Popen([editor, "--diff", str(source), str(py_path)])
        console.print(f"[green]Opened diff in {editor}.[/green]")
    except FileNotFoundError:
        _print_manual_diff(source, py_path, editor, f"Editor '{editor}' not found.")
    except OSError as exc:
        _print_manual_diff(
            source,
            py_path,
            editor,
            f"Editor '{editor}' could not be launched: {exc}",
        )


def _print_manual_diff(source: Path, py_path: Path, editor: str, message: str) -> None:
    console.print(f"[yellow]{message}[/yellow] To open the diff manually, run:")
    console.print(f"  {editor} --diff {source} {py_path}", soft_wrap=True)
    console.print(f"\nJava:   {source}", soft_wrap=True)
    console.print(f"Python: {py_path}", soft_wrap=True)


def _load_config(config: list[Path]) -> TranslationConfig:
    from j2py.config.loader import ConfigLoader

    loader = ConfigLoader().add_defaults()
    for c in config:
        loader.add_file(c)
    return loader.build()


def _print_result_summary(result: TranslationResult) -> None:
    diagnostics = result.diagnostics
    handled = len(diagnostics.handled) if diagnostics is not None else 0
    unhandled = len(diagnostics.unhandled) if diagnostics is not None else 0
    console.print(
        f"[dim]{result.source_path.name}: confidence={result.confidence:.2f}, "
        f"handled={handled}, unhandled={unhandled}, llm={result.used_llm}[/dim]",
    )
    if result.validation is not None:
        _print_validation(result.validation)


def _print_validation(validation: ValidationResult) -> None:
    if validation.ok:
        console.print("[green]Validation passed[/green]")
        return
    console.print("[yellow]Validation issues:[/yellow]")
    for err in validation.syntax_errors + validation.mypy_errors + validation.ruff_errors:
        console.print(f"  {err}")


if __name__ == "__main__":
    app()
