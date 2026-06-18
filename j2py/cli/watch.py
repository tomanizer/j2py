"""Implementation for the ``j2py watch`` command."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from j2py.cli.config import LLMProvider, load_config, resolve_llm_options
from j2py.cli.output import console
from j2py.cli.translate import (
    emit_runtime_module,
    refresh_directory_state,
    write_directory_translation_results,
    write_translation_result,
)

if TYPE_CHECKING:
    from j2py.config.loader import TranslationConfig


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
        help="LLM provider to use for completion: anthropic, gemini, or openai. Overrides config.",
    ),
    llm_base_url: str | None = typer.Option(
        None,
        "--llm-base-url",
        help="Base URL for OpenAI-compatible providers. Overrides config and OPENAI_BASE_URL.",
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
    if not source.exists():
        console.print(f"[red]Error:[/red] source path not found: {source}")
        raise typer.Exit(code=1)

    cfg = load_config(config, source if source.is_dir() else source.parent)
    if llm_base_url is not None:
        cfg = cfg.model_copy(update={"llm_base_url": llm_base_url})
    provider, effective_model = resolve_llm_options(cfg, llm_provider, model)
    console.print(f"[bold]Watching[/bold] {source} → {output}")
    seen = _java_hashes(source)
    run_watch_translation(source, output, cfg, llm, effective_model, provider, validate)
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
                run_watch_translation(source, output, cfg, llm, effective_model, provider, validate)
                seen = current
    except KeyboardInterrupt:
        console.print("[yellow]Stopped.[/yellow]")


def _java_hashes(source: Path) -> dict[Path, str]:
    from j2py.state import sha256_file

    files = sorted(source.rglob("*.java")) if source.is_dir() else [source]
    return {path: sha256_file(path) for path in files if path.exists()}


def run_watch_translation(
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
        write_directory_translation_results(batch, cfg)
        emit_runtime_module(output, [result.python_source for result in batch.files])
        refresh_directory_state(batch, source_root=source, output_root=output)
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
    write_translation_result(result, output, cfg)
    emit_runtime_module(output.parent, [result.python_source])
    timestamp = time.strftime("%H:%M:%S")
    console.print(
        f"[{timestamp}] Translated {source.name} → {output.name} "
        f"(confidence: {result.confidence:.0%})",
    )
