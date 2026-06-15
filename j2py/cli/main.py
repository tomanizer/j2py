"""j2py CLI — Java to Python converter."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import networkx as nx
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from j2py.analyze.symbols import ClassSymbol
from j2py.pipeline import PARSE_ERROR_LLM_SKIP_MSG

if TYPE_CHECKING:
    from j2py.config.loader import TranslationConfig
    from j2py.pipeline import DirectoryTranslationResult, TranslationResult
    from j2py.validate.checks import ValidationResult
    from j2py.verify.structure import StructuralVerificationResult

app = typer.Typer(
    name="j2py",
    help="Convert Java source files to Python.",
    add_completion=False,
)
console = Console()
LLMProvider = Literal["anthropic", "gemini"]


def _normalize_llm_provider(value: str) -> LLMProvider:
    normalized = value.lower()
    if normalized not in {"anthropic", "gemini"}:
        raise typer.BadParameter(
            "unsupported LLM provider; choose 'anthropic' or 'gemini'",
            param_hint="--llm-provider",
        )
    return cast(LLMProvider, normalized)


def _resolve_llm_options(
    cfg: TranslationConfig,
    llm_provider: str | None,
    model: str | None,
) -> tuple[LLMProvider, str | None]:
    provider = (
        _normalize_llm_provider(llm_provider)
        if llm_provider is not None
        else cfg.llm_provider or "anthropic"
    )
    effective_model = model if model is not None else cfg.model
    return provider, effective_model


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
    validate: bool = typer.Option(
        True, "--validate/--no-validate", help="Run mypy + ruff on output."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print translated output, do not write files."
    ),
    report: Path | None = typer.Option(
        None,
        "--report",
        help="Write a self-contained HTML side-by-side review report.",
    ),
    dashboard: Path | None = typer.Option(
        None,
        "--dashboard",
        help="Write a self-contained directory translation dashboard.",
    ),
    incremental: bool = typer.Option(
        False,
        "--incremental",
        help="Skip unchanged directory files using .j2py-state.json.",
    ),
    workers: int | None = typer.Option(
        None,
        "--workers",
        min=1,
        help="Directory translation worker threads. Defaults to config workers.",
    ),
    llm_concurrency: int | None = typer.Option(
        None,
        "--llm-concurrency",
        min=1,
        help="Maximum concurrent LLM calls during directory translation.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable translation result JSON.",
    ),
) -> None:
    """Translate a Java file or directory tree to Python."""
    cfg = _load_config(config, source if source.is_dir() else source.parent)
    provider, effective_model = _resolve_llm_options(cfg, llm_provider, model)

    if source.is_dir():
        _translate_dir(
            source,
            output or source.parent / (source.name + "_py"),
            cfg,
            llm,
            effective_model,
            provider,
            validate,
            dry_run,
            report,
            dashboard,
            incremental,
            workers,
            llm_concurrency,
            json_output,
        )
    else:
        _translate_single(
            source,
            output,
            cfg,
            llm,
            effective_model,
            provider,
            validate,
            dry_run,
            report,
            json_output,
        )


def _translate_single(
    source: Path,
    output: Path | None,
    cfg: TranslationConfig,
    llm: bool,
    model: str | None,
    llm_provider: LLMProvider,
    validate: bool,
    dry_run: bool,
    report: Path | None,
    json_output: bool,
) -> None:
    from j2py.pipeline import translate_file

    if not json_output:
        console.print(f"[bold]Translating[/bold] {source}")
    result = translate_file(
        source,
        cfg=cfg,
        use_llm=llm,
        model=model,
        llm_provider=llm_provider,
        validate=validate,
    )
    if json_output:
        console.print(json.dumps(_result_payload(result), indent=2, sort_keys=True))
    else:
        _print_result_summary(result)

    if dry_run:
        if not json_output:
            console.print(result.python_source)
        if _result_has_blocking_issues(result, validate=validate):
            raise typer.Exit(code=1)
        return

    dest = output or source.with_suffix(".py")
    dest.write_text(result.python_source)
    if not json_output:
        console.print(f"[green]Written:[/green] {dest}")
    _emit_runtime_module(dest.parent, [result.python_source], quiet=json_output)
    if report is not None:
        from j2py.report import write_translation_report

        write_translation_report(report, [result])
        if not json_output:
            console.print(f"[green]Report:[/green] {report}")

    if validate and result.validation is not None and not json_output:
        _print_validation(result.validation)
    if result.structural_verification is not None and not json_output:
        _print_structural_verification(result.structural_verification)
    if _result_has_blocking_issues(result, validate=validate):
        raise typer.Exit(code=1)


def _emit_runtime_module(output_root: Path, sources: list[str], *, quiet: bool = False) -> None:
    """Vendor j2py_runtime.py next to translated output when runtime helpers are used."""
    from j2py.translate.runtime import (
        RUNTIME_MODULE_NAME,
        runtime_module_source,
    )

    if not any(f"from {RUNTIME_MODULE_NAME} import " in source for source in sources):
        return
    runtime_path = output_root / f"{RUNTIME_MODULE_NAME}.py"
    runtime_path.write_text(runtime_module_source())
    if not quiet:
        console.print(f"[green]Written:[/green] {runtime_path} (j2py runtime helpers)")


def _translate_dir(
    source: Path,
    output: Path,
    cfg: TranslationConfig,
    llm: bool,
    model: str | None,
    llm_provider: LLMProvider,
    validate: bool,
    dry_run: bool,
    report: Path | None,
    dashboard: Path | None,
    incremental: bool,
    workers: int | None,
    llm_concurrency: int | None,
    json_output: bool,
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
        llm_provider=llm_provider,
        validate=validate,
        workers=workers or cfg.workers,
        llm_concurrency=llm_concurrency or cfg.llm_concurrency,
        incremental=incremental,
    )
    if json_output:
        console.print(json.dumps(_directory_payload(batch), indent=2, sort_keys=True))
    else:
        console.print("[bold]Translation order:[/bold]")
        for index, path in enumerate(batch.order, start=1):
            console.print(f"  {index}. {path.relative_to(source)}")
        for warning in batch.warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")
        if incremental:
            console.print(
                f"[dim]{batch.skipped_count} files skipped, "
                f"{batch.translated_count} re-translated[/dim]",
            )

    if not dry_run:
        output.mkdir(parents=True, exist_ok=True)

    if json_output:
        for result in batch.files:
            if not dry_run and result.output_path is not None and not result.skipped:
                result.output_path.parent.mkdir(parents=True, exist_ok=True)
                result.output_path.write_text(result.python_source)
    else:
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Writing...", total=len(batch.files))
            for result in batch.files:
                progress.update(task, description=f"[cyan]{result.source_path.name}[/cyan]")
                _print_result_summary(result)
                if dry_run:
                    console.print(f"\n[bold]{result.source_path}[/bold]")
                    console.print(result.python_source)
                elif result.output_path is not None and not result.skipped:
                    result.output_path.parent.mkdir(parents=True, exist_ok=True)
                    result.output_path.write_text(result.python_source)
                progress.advance(task)

    if not dry_run:
        from j2py.state import entry_from_result, load_state, save_state, source_key

        _emit_runtime_module(
            output,
            [result.python_source for result in batch.files],
            quiet=json_output,
        )
        previous_entries = load_state(output)
        entries = {}
        for result in batch.files:
            key = source_key(result.source_path, source)
            if result.skipped and key in previous_entries:
                entries[key] = previous_entries[key]
            else:
                entries[key] = entry_from_result(
                    result,
                    source_root=source,
                    output_root=output,
                )
        save_state(output, entries)
        if report is not None:
            from j2py.report import write_translation_report

            write_translation_report(report, batch.files)
            if not json_output:
                console.print(f"[green]Report:[/green] {report}")
        if dashboard is not None:
            from j2py.dashboard import write_dashboard_for_results

            write_dashboard_for_results(
                dashboard,
                batch.files,
                source_root=source,
                output_root=output,
            )
            if not json_output:
                console.print(f"[green]Dashboard:[/green] {dashboard}")

    if not json_output:
        console.print(f"[green]Done.[/green] {len(batch.files)} files → {output}")
    failures = [
        result for result in batch.files if _result_has_blocking_issues(result, validate=validate)
    ]
    if failures:
        console.print("[yellow]Translation verification failures:[/yellow]")
        for result in failures:
            console.print(f"  {result.source_path}")
            if result.validation is not None:
                _print_validation(result.validation)
            if result.structural_verification is not None:
                _print_structural_verification(result.structural_verification)
        raise typer.Exit(code=1)


@app.command()
def dashboard(
    output_root: Path = typer.Argument(..., help="Directory containing .j2py-state.json."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Dashboard HTML path. Defaults to <output-root>/dashboard.html.",
    ),
) -> None:
    """Regenerate a dashboard from an existing translation state file."""
    from j2py.dashboard import write_dashboard_from_state

    dashboard_path = output or output_root / "dashboard.html"
    write_dashboard_from_state(output_root, dashboard_path)
    console.print(f"[green]Dashboard:[/green] {dashboard_path}")


@app.command()
def watch(
    source: Path = typer.Argument(..., help="Java file or directory to watch."),
    output: Path = typer.Option(..., "--output", "-o", help="Output file or directory."),
    config: list[Path] = typer.Option(
        [], "--config", "-c", help="Extra config file(s) to layer on top of defaults."
    ),
    llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use LLM completion for unresolved logic.",
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
    validate: bool = typer.Option(
        True, "--validate/--no-validate", help="Run mypy + ruff on output."
    ),
    poll_interval: float = typer.Option(
        0.5,
        "--poll-interval",
        min=0.1,
        help="Polling interval in seconds.",
    ),
) -> None:
    """Watch Java sources and incrementally re-translate changes until interrupted."""
    cfg = _load_config(config, source if source.is_dir() else source.parent)
    provider, effective_model = _resolve_llm_options(cfg, llm_provider, model)
    console.print(f"[bold]Watching[/bold] {source} → {output}")
    seen = _java_hashes(source)
    _run_watch_translation(source, output, cfg, llm, effective_model, provider, validate)
    try:
        while True:
            time.sleep(poll_interval)
            current = _java_hashes(source)
            changed = sorted(path for path, digest in current.items() if seen.get(path) != digest)
            removed = sorted(path for path in seen if path not in current)
            if changed or removed:
                timestamp = time.strftime("%H:%M:%S")
                for path in changed:
                    console.print(f"[{timestamp}] Changed {path.name}")
                for path in removed:
                    console.print(f"[{timestamp}] Removed {path.name}")
                _run_watch_translation(
                    source, output, cfg, llm, effective_model, provider, validate
                )
                seen = current
    except KeyboardInterrupt:
        console.print("[yellow]Stopped.[/yellow]")


@app.command()
def analyze(
    source: Path = typer.Argument(..., help="Java file or directory to analyze."),
) -> None:
    """Print class inventory, dependency graph, and parse-error status without translating."""
    from j2py.analyze.graph import build_dependency_graph
    from j2py.analyze.symbols import extract_symbols
    from j2py.parse.java_ast import parse_file

    java_files = sorted(source.rglob("*.java")) if source.is_dir() else [source]
    if not java_files:
        console.print("[yellow]No .java files found.[/yellow]")
        return

    all_symbols = []
    for jf in java_files:
        parsed = parse_file(jf)
        symbols = extract_symbols(parsed)
        all_symbols.append(symbols)
        console.print(f"\n[bold]{jf}[/bold] — package: {symbols.package}")
        if parsed.has_errors:
            console.print("  [yellow]Parse errors detected in source[/yellow]")
        for cls in symbols.classes:
            _print_class_inventory(cls, indent=2)

    graph = build_dependency_graph(all_symbols)
    root = source if source.is_dir() else source.parent
    _print_dependency_graph(graph, root=root)


def _print_class_inventory(cls: ClassSymbol, *, indent: int) -> None:
    console.print(_format_class_inventory_line(cls, indent=indent))
    for inner in cls.inner_classes:
        _print_class_inventory(inner, indent=indent + 2)


def _format_class_inventory_line(cls: ClassSymbol, *, indent: int) -> str:
    kind = _class_kind(cls)
    padding = " " * indent
    return f"{padding}{cls.name} ({kind}) — {len(cls.methods)} methods, {len(cls.fields)} fields"


def _class_kind(cls: ClassSymbol) -> str:
    if cls.is_interface:
        return "interface"
    if cls.is_enum:
        return "enum"
    if cls.is_record:
        return "record"
    return "class"


def _relative_display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def _print_dependency_graph(graph: nx.DiGraph, *, root: Path) -> None:
    if graph.number_of_nodes() == 0:
        return

    console.print("\n[bold]Dependency graph[/bold] (A → B means A depends on B):")
    edges = sorted(graph.edges(), key=lambda edge: (edge[0], edge[1]))
    if edges:
        for src, dep in edges:
            console.print(
                f"  {_relative_display_path(Path(src), root)}"
                f" → {_relative_display_path(Path(dep), root)}"
            )
    else:
        console.print("  [dim]No cross-file dependencies resolved[/dim]")

    import warnings

    from j2py.analyze.graph import translation_order

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        order = translation_order(graph)
    for warning in caught:
        console.print(f"[yellow]Warning:[/yellow] {warning.message}")

    console.print("\n[bold]Translation order:[/bold]")
    for index, path in enumerate(order, start=1):
        console.print(f"  {index}. {_relative_display_path(Path(path), root)}")


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

        cfg = _load_config(config, source.parent)
        provider, effective_model = _resolve_llm_options(cfg, llm_provider, model)
        console.print(f"[bold]Translating[/bold] {source}")
        result = translate_file(
            source,
            cfg=cfg,
            use_llm=llm,
            model=effective_model,
            llm_provider=provider,
            validate=validate,
        )
        _print_result_summary(result)
        py_path.parent.mkdir(parents=True, exist_ok=True)
        py_path.write_text(result.python_source)
        console.print(f"[green]Written:[/green] {py_path}")
        _emit_runtime_module(py_path.parent, [result.python_source])

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
    args = [editor]
    editor_name = Path(editor).name.lower()
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


def _load_config(config: list[Path], auto_root: Path | None = None) -> TranslationConfig:
    from j2py.config.loader import ConfigError, ConfigLoader

    loader = ConfigLoader().add_defaults()
    try:
        if config:
            for c in config:
                loader.add_file(c)
        elif auto_root is not None:
            loader.add_auto_discovered(auto_root)
        return loader.build()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc


def _result_payload(result: TranslationResult) -> dict[str, object]:
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
        "todos": _todo_lines(result.python_source),
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


def _directory_payload(batch: DirectoryTranslationResult) -> dict[str, object]:
    return {
        "source_root": str(batch.source_root),
        "output_root": str(batch.output_root),
        "skipped": batch.skipped_count,
        "translated": batch.translated_count,
        "warnings": batch.warnings,
        "files": [_result_payload(result) for result in batch.files],
    }


def _todo_lines(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if "TODO(j2py)" in line or "__j2py_todo__" in line
    ]


def _java_hashes(source: Path) -> dict[Path, str]:
    from j2py.state import sha256_file

    files = sorted(source.rglob("*.java")) if source.is_dir() else [source]
    return {path: sha256_file(path) for path in files if path.exists()}


def _run_watch_translation(
    source: Path,
    output: Path,
    cfg: TranslationConfig,
    llm: bool,
    model: str | None,
    llm_provider: LLMProvider,
    validate: bool,
) -> None:
    from j2py.pipeline import translate_directory, translate_file

    if source.is_dir():
        batch = translate_directory(
            source,
            output,
            cfg=cfg,
            use_llm=llm,
            model=model,
            llm_provider=llm_provider,
            validate=validate,
            incremental=True,
            workers=cfg.workers,
            llm_concurrency=cfg.llm_concurrency,
        )
        output.mkdir(parents=True, exist_ok=True)
        for result in batch.files:
            if result.output_path is not None and not result.skipped:
                result.output_path.parent.mkdir(parents=True, exist_ok=True)
                result.output_path.write_text(result.python_source)
        _emit_runtime_module(output, [result.python_source for result in batch.files])
        from j2py.state import entry_from_result, load_state, save_state, source_key

        previous_entries = load_state(output)
        entries = {}
        for result in batch.files:
            key = source_key(result.source_path, source)
            if result.skipped and key in previous_entries:
                entries[key] = previous_entries[key]
            else:
                entries[key] = entry_from_result(
                    result,
                    source_root=source,
                    output_root=output,
                )
        save_state(
            output,
            entries,
        )
        timestamp = time.strftime("%H:%M:%S")
        console.print(
            f"[{timestamp}] {batch.skipped_count} files skipped, "
            f"{batch.translated_count} re-translated",
        )
        return

    result = translate_file(
        source,
        cfg=cfg,
        use_llm=llm,
        model=model,
        llm_provider=llm_provider,
        validate=validate,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.python_source)
    _emit_runtime_module(output.parent, [result.python_source])
    timestamp = time.strftime("%H:%M:%S")
    console.print(
        f"[{timestamp}] Translated {source.name} → {output.name} "
        f"(confidence: {result.confidence:.0%})",
    )


def _print_result_summary(result: TranslationResult) -> None:
    diagnostics = result.diagnostics
    handled = len(diagnostics.handled) if diagnostics is not None else 0
    unhandled = len(diagnostics.unhandled) if diagnostics is not None else 0
    parse_note = "" if result.parse_ok else ", parse_ok=False"
    console.print(
        f"[dim]{result.source_path.name}: confidence={result.confidence:.2f}, "
        f"handled={handled}, unhandled={unhandled}, llm={result.used_llm}{parse_note}[/dim]",
    )
    if not result.parse_ok:
        console.print(f"[yellow]Warning:[/yellow] {PARSE_ERROR_LLM_SKIP_MSG}")
    if result.validation is not None:
        _print_validation(result.validation)
    if result.structural_verification is not None:
        _print_structural_verification(result.structural_verification)


def _print_validation(validation: ValidationResult) -> None:
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


def _print_structural_verification(verification: StructuralVerificationResult) -> None:
    if verification.ok:
        console.print("[green]Structural verification passed[/green]")
        return
    console.print("[yellow]Structural verification issues:[/yellow]")
    for err in verification.errors:
        console.print(f"  {err}")


def _result_has_blocking_issues(result: TranslationResult, *, validate: bool) -> bool:
    validation_failed = validate and result.validation is not None and not result.validation.ok
    structural_failed = (
        result.structural_verification is not None and not result.structural_verification.ok
    )
    return validation_failed or structural_failed


if __name__ == "__main__":
    app()
