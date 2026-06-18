"""Implementation for the ``j2py translate`` command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from j2py.cli.config import (
    LLMProvider,
    LlmReviewScope,
    load_config,
    normalize_llm_review_scope,
    resolve_llm_options,
)
from j2py.cli.output import (
    console,
    directory_payload,
    print_result_summary,
    print_structural_verification,
    print_validation,
    result_has_blocking_issues,
    result_payload,
)

if TYPE_CHECKING:
    from j2py.config.loader import TranslationConfig
    from j2py.pipeline import DirectoryTranslationResult, TranslationResult


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
        help="LLM provider to use for completion: anthropic, gemini, or openai. Overrides config.",
    ),
    llm_base_url: str | None = typer.Option(
        None,
        "--llm-base-url",
        help="Base URL for OpenAI-compatible providers. Overrides config and OPENAI_BASE_URL.",
    ),
    llm_review: bool = typer.Option(
        False,
        "--llm-review",
        help="Run an opt-in, non-mutating LLM review pass after translation.",
    ),
    llm_review_scope: str = typer.Option(
        "all",
        "--llm-review-scope",
        help="Files to review when --llm-review is enabled: all, warnings, or low-confidence.",
    ),
    review_report: Path | None = typer.Option(
        None,
        "--review-report",
        help="Write machine-readable LLM review findings JSON.",
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
    if not source.exists():
        console.print(f"[red]Error:[/red] source path not found: {source}")
        raise typer.Exit(code=1)

    cfg = load_config(config, source if source.is_dir() else source.parent)
    if llm_base_url is not None:
        cfg = cfg.model_copy(update={"llm_base_url": llm_base_url})
    provider, effective_model = resolve_llm_options(cfg, llm_provider, model)
    effective_review_scope = normalize_llm_review_scope(llm_review_scope)

    if source.is_dir():
        _translate_dir(
            source,
            output or source.parent / (source.name + "_py"),
            cfg,
            llm,
            effective_model,
            provider,
            llm_review,
            effective_review_scope,
            validate,
            dry_run,
            report,
            dashboard,
            review_report,
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
            llm_review,
            effective_review_scope,
            validate,
            dry_run,
            report,
            review_report,
            json_output,
        )


def _translate_single(
    source: Path,
    output: Path | None,
    cfg: TranslationConfig,
    llm: bool,
    model: str | None,
    llm_provider: LLMProvider,
    llm_review: bool,
    llm_review_scope: LlmReviewScope,
    validate: bool,
    dry_run: bool,
    report: Path | None,
    review_report: Path | None,
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
        llm_review=llm_review,
        llm_review_scope=llm_review_scope,
        validate=validate,
    )
    if json_output:
        typer.echo(json.dumps(result_payload(result), indent=2, sort_keys=True))
    else:
        print_result_summary(result)

    if dry_run:
        if review_report is not None:
            write_review_report(review_report, [result])
        if not json_output:
            console.print(result.python_source)
        if result_has_blocking_issues(result, validate=validate):
            raise typer.Exit(code=1)
        return

    dest = output or source.with_suffix(".py")
    write_translation_result(result, dest, cfg)
    if not json_output:
        console.print(f"[green]Written:[/green] {dest}")
    emit_runtime_module(dest.parent, [result.python_source], quiet=json_output)
    if report is not None:
        from j2py.report import write_translation_report

        write_translation_report(report, [result])
        if not json_output:
            console.print(f"[green]Report:[/green] {report}")
    if review_report is not None:
        write_review_report(review_report, [result])
        if not json_output:
            console.print(f"[green]Review report:[/green] {review_report}")

    if validate and result.validation is not None and not json_output:
        print_validation(result.validation)
    if result.structural_verification is not None and not json_output:
        print_structural_verification(result.structural_verification)
    if result_has_blocking_issues(result, validate=validate):
        raise typer.Exit(code=1)


def emit_runtime_module(output_root: Path, sources: list[str], *, quiet: bool = False) -> None:
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


def write_translation_result(
    result: TranslationResult,
    output_path: Path,
    cfg: TranslationConfig,
) -> None:
    from j2py.pipeline import write_wiring_metadata_sidecar

    result.output_path = output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.python_source)
    if cfg.emit_wiring_metadata:
        write_wiring_metadata_sidecar(result)


def write_directory_translation_results(
    batch: DirectoryTranslationResult,
    cfg: TranslationConfig,
) -> None:
    for result in batch.files:
        if result.output_path is not None and not result.skipped:
            write_translation_result(result, result.output_path, cfg)


def refresh_directory_state(
    batch: DirectoryTranslationResult,
    *,
    source_root: Path,
    output_root: Path,
) -> None:
    from j2py.state import entry_from_result, load_state, save_state, source_key

    previous_entries = load_state(output_root)
    entries = {}
    for result in batch.files:
        key = source_key(result.source_path, source_root)
        if result.skipped and key in previous_entries:
            entries[key] = previous_entries[key]
        else:
            entries[key] = entry_from_result(
                result,
                source_root=source_root,
                output_root=output_root,
            )
    save_state(output_root, entries)


def write_review_report(path: Path, results: list[TranslationResult]) -> None:
    from j2py.cli.output import result_payload

    file_payloads = [result_payload(result) for result in results]
    payload = {
        "files": [
            {
                "file": item["file"],
                "output": item["output"],
                "llm_review_ran": item["llm_review_ran"],
                "llm_review_findings": item["llm_review_findings"],
                "llm_review_error": item["llm_review_error"],
            }
            for item in file_payloads
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _translate_dir(
    source: Path,
    output: Path,
    cfg: TranslationConfig,
    llm: bool,
    model: str | None,
    llm_provider: LLMProvider,
    llm_review: bool,
    llm_review_scope: LlmReviewScope,
    validate: bool,
    dry_run: bool,
    report: Path | None,
    dashboard: Path | None,
    review_report: Path | None,
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
        llm_review=llm_review,
        llm_review_scope=llm_review_scope,
        validate=validate,
        workers=workers or cfg.workers,
        llm_concurrency=llm_concurrency or cfg.llm_concurrency,
        incremental=incremental,
    )
    if json_output:
        typer.echo(json.dumps(directory_payload(batch), indent=2, sort_keys=True))
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
        if not dry_run:
            write_directory_translation_results(batch, cfg)
    else:
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Writing...", total=len(batch.files))
            for result in batch.files:
                progress.update(task, description=f"[cyan]{result.source_path.name}[/cyan]")
                print_result_summary(result)
                if dry_run:
                    console.print(f"\n[bold]{result.source_path}[/bold]")
                    console.print(result.python_source)
                elif result.output_path is not None and not result.skipped:
                    write_translation_result(result, result.output_path, cfg)
                progress.advance(task)

    if not dry_run:
        emit_runtime_module(
            output,
            [result.python_source for result in batch.files],
            quiet=json_output,
        )
        refresh_directory_state(batch, source_root=source, output_root=output)
        if report is not None:
            from j2py.report import write_translation_report

            write_translation_report(report, batch.files)
            if not json_output:
                console.print(f"[green]Report:[/green] {report}")
        if dashboard is not None:
            from j2py.report import write_dashboard_for_results

            write_dashboard_for_results(
                dashboard,
                batch.files,
                source_root=source,
                output_root=output,
            )
            if not json_output:
                console.print(f"[green]Dashboard:[/green] {dashboard}")
        if review_report is not None:
            write_review_report(review_report, batch.files)
            if not json_output:
                console.print(f"[green]Review report:[/green] {review_report}")
    elif review_report is not None:
        write_review_report(review_report, batch.files)

    if not json_output:
        console.print(f"[green]Done.[/green] {len(batch.files)} files → {output}")
    failures = [
        result for result in batch.files if result_has_blocking_issues(result, validate=validate)
    ]
    if failures:
        console.print("[yellow]Translation verification failures:[/yellow]")
        for result in failures:
            console.print(f"  {result.source_path}")
            if result.validation is not None:
                print_validation(result.validation)
            if result.structural_verification is not None:
                print_structural_verification(result.structural_verification)
        raise typer.Exit(code=1)
