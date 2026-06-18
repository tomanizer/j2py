"""Implementation for the ``j2py compare`` command."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import typer

from j2py.cli.config import load_config, resolve_llm_options
from j2py.cli.output import console, print_result_summary
from j2py.cli.translate import emit_runtime_module, write_translation_result


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
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider to use for completion: anthropic or gemini. Overrides config.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="LLM model ID to use. Defaults depend on --llm-provider.",
    ),
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
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Run mypy + ruff during generated translation.",
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

        cfg = load_config(config, source.parent)
        provider, effective_model = resolve_llm_options(cfg, llm_provider, model)
        console.print(f"[bold]Translating[/bold] {source}")
        result = translate_file(
            source,
            cfg=cfg,
            use_llm=llm,
            model=effective_model,
            llm_provider=provider,
            validate=validate,
        )
        print_result_summary(result)
        write_translation_result(result, py_path, cfg)
        console.print(f"[green]Written:[/green] {py_path}")
        emit_runtime_module(py_path.parent, [result.python_source])

    if no_open:
        console.print(f"Java:   {source}", soft_wrap=True)
        console.print(f"Python: {py_path}", soft_wrap=True)
        diff_command = _format_command(_diff_args(source, py_path, editor))
        console.print(f"Diff:   {diff_command}", soft_wrap=True)
        return

    _open_diff(source, py_path, editor)


def _resolve_py_path(source: Path, output: Path | None) -> Path:
    return output if output is not None else source.with_suffix(".py")


def _open_diff(source: Path, py_path: Path, editor: str) -> None:
    args = _diff_args(source, py_path, editor)
    try:
        subprocess.Popen(args)
        console.print(f"[green]Opened diff in {editor}.[/green]")
    except FileNotFoundError:
        _print_manual_diff(source, py_path, args, f"Editor '{editor}' not found.")
    except OSError as exc:
        _print_manual_diff(
            source,
            py_path,
            args,
            f"Editor '{editor}' could not be launched: {exc}",
        )


def _diff_args(source: Path, py_path: Path, editor: str) -> list[str]:
    args = shlex.split(editor, posix=sys.platform != "win32")
    if sys.platform == "win32":
        args = [arg.strip("\"'") for arg in args]
    if not args:
        args = [editor]
    editor_name = Path(args[0]).name.lower()
    if "code" in editor_name or "cursor" in editor_name:
        args.append("--diff")
    args.extend([str(source), str(py_path)])
    return args


def _format_command(args: list[str]) -> str:
    return " ".join(args)


def _print_manual_diff(source: Path, py_path: Path, args: list[str], message: str) -> None:
    console.print(f"[yellow]{message}[/yellow] To open the diff manually, run:")
    console.print(f"  {_format_command(args)}", soft_wrap=True)
    console.print(f"\nJava:   {source}", soft_wrap=True)
    console.print(f"Python: {py_path}", soft_wrap=True)
