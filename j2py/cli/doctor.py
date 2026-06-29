"""Doctor, dashboard, and SARIF CLI adapters."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from tenacity import RetryError

from j2py.cli.config import load_config, resolve_llm_options
from j2py.cli.output import console
from j2py.doctor import DoctorAssessment

doctor_app = typer.Typer(help="Assess projects and produce migration advice.")


def _load_assessment(path: Path) -> tuple[DoctorAssessment | None, int]:
    """Load an assessment and return (payload, exit_code)."""
    try:
        from j2py.doctor import load_assessment_json

        return load_assessment_json(path), 0
    except (OSError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return None, 1


@doctor_app.command()
def assess(
    source: Path = typer.Argument(..., help="Java file or directory to assess."),
    config: list[Path] = typer.Option(
        [], "--config", "-c", help="Extra config file(s) to layer on top of defaults."
    ),
    json_path: Path | None = typer.Option(
        None,
        "--json",
        help="Write machine-readable assessment JSON.",
    ),
    html_path: Path | None = typer.Option(
        None,
        "--html",
        help="Write a static HTML assessment report.",
    ),
    config_suggestions_path: Path | None = typer.Option(
        None,
        "--config-suggestions",
        help="Write advisory config suggestions YAML.",
    ),
    include_validation: bool = typer.Option(
        False,
        "--include-validation",
        help="Run Python syntax, ruff, and mypy checks on rule-only translations.",
    ),
    sample_limit: int | None = typer.Option(
        None,
        "--sample-limit",
        min=1,
        help="Assess only the first N Java files in deterministic path order.",
    ),
) -> None:
    """Assess a Java project before migration without live LLM calls."""
    from j2py.doctor import (
        assess_project,
        write_assessment_html,
        write_assessment_json,
        write_config_suggestions,
    )

    if not source.exists():
        console.print(f"[red]Error:[/red] source path not found: {source}")
        raise typer.Exit(code=1)

    cfg = load_config(config, source if source.is_dir() else source.parent)
    assessment = assess_project(
        source,
        cfg=cfg,
        include_validation=include_validation,
        sample_limit=sample_limit,
    )
    if json_path is not None:
        write_assessment_json(json_path, assessment)
        console.print(f"[green]Assessment JSON:[/green] {json_path}")
    if html_path is not None:
        write_assessment_html(html_path, assessment)
        console.print(f"[green]Assessment HTML:[/green] {html_path}")
    if config_suggestions_path is not None:
        write_config_suggestions(config_suggestions_path, assessment)
        console.print(f"[green]Config suggestions:[/green] {config_suggestions_path}")

    if json_path is None and html_path is None and config_suggestions_path is None:
        typer.echo(assessment.to_json())
        return

    summary = assessment.payload["summary"]
    readiness = {item["bucket"]: item["files"] for item in summary["readiness_distribution"]}
    console.print(
        "[bold]Doctor assessment:[/bold] "
        f"{summary['files']} files, "
        f"{summary['parse_failures']} parse failures, "
        f"{summary['semantic_warnings']} semantic warnings, "
        f"{summary['unhandled_diagnostics']} unhandled diagnostics",
        f"risk={summary['average_risk_score']:.1f}, "
        f"ready={readiness['ready']}, manual={readiness['requires_manual_fixes']}, "
        f"not_ready={readiness['not_ready']}",
    )


@doctor_app.command()
def diff(
    before_json: Path = typer.Argument(..., help="Assessment JSON before changes."),
    after_json: Path = typer.Argument(..., help="Assessment JSON after changes."),
    json_path: Path | None = typer.Option(
        None,
        "--json",
        help="Write machine-readable doctor diff JSON.",
    ),
) -> None:
    """Compare doctor assessment JSON files."""
    from j2py.doctor import (
        diff_assessments,
        render_doctor_diff_text,
        write_doctor_diff_json,
    )

    before_result, code = _load_assessment(before_json)
    after_result, after_code = _load_assessment(after_json)
    if code or after_code:
        raise typer.Exit(code=max(code, after_code))

    if before_result is None or after_result is None:
        raise typer.Exit(code=1)
    try:
        diff_result = diff_assessments(
            before_result,
            after_result,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_path is not None:
        write_doctor_diff_json(json_path, diff_result)
        console.print(f"[green]Doctor diff JSON:[/green] {json_path}")
    typer.echo(render_doctor_diff_text(diff_result), nl=False)


@doctor_app.command()
def advise(
    assessment_json: Path = typer.Argument(..., help="Doctor assessment JSON to advise from."),
    config: list[Path] = typer.Option(
        [],
        "--config",
        "-c",
        help="Extra config file(s) to layer on top of defaults.",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        "--llm-provider",
        help="LLM provider to use for advice: anthropic, gemini, or openai. Overrides config.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="LLM model ID to use. Defaults depend on --provider.",
    ),
    llm_base_url: str | None = typer.Option(
        None,
        "--llm-base-url",
        help="Base URL for OpenAI-compatible providers. Overrides config and OPENAI_BASE_URL.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write output to PATH (defaults to stdout).",
    ),
    output_format: str = typer.Option(
        "markdown",
        "--output-format",
        help="Output format for command output (markdown or json).",
    ),
    max_evidence_items: int = typer.Option(
        12,
        "--max-evidence-items",
        min=1,
        help="Cap per-section evidence examples used in the prompt.",
    ),
    use_cache: bool = typer.Option(
        True,
        "--cache/--no-cache",
        help="Cache LLM advice responses by provider/model/context fingerprint.",
    ),
) -> None:
    """Generate migration advice from a deterministic doctor assessment."""
    from j2py.doctor_advice import (
        build_doctor_advice_context,
        render_doctor_advice_json,
    )
    from j2py.llm.client import advise_with_doctor_assessment, resolve_model

    normalized_output_format = output_format.lower()
    if normalized_output_format not in {"markdown", "json"}:
        console.print(
            f"[red]Error:[/red] unsupported output format: {output_format!r}; use markdown or json"
        )
        raise typer.Exit(code=2)

    assessment, code = _load_assessment(assessment_json)
    if code:
        raise typer.Exit(code=code)
    if assessment is None:
        raise typer.Exit(code=1)

    auto_root = assessment_json.parent
    source_hint = assessment.payload.get("source")
    if isinstance(source_hint, str):
        source_path = Path(source_hint)
        if not source_path.is_absolute():
            source_path = assessment_json.parent / source_path
        if source_path.exists():
            auto_root = source_path.parent if source_path.is_file() else source_path

    cfg = load_config(config, auto_root)
    if llm_base_url is not None:
        cfg = cfg.model_copy(update={"llm_base_url": llm_base_url})
    try:
        resolved_provider, resolved_model = resolve_llm_options(cfg, provider, model)
        resolved_model = resolve_model(resolved_provider, resolved_model)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    evidence, evidence_fingerprint, _ = build_doctor_advice_context(
        assessment,
        max_evidence_items=max_evidence_items,
    )

    try:
        advice_markdown = advise_with_doctor_assessment(
            evidence=evidence,
            evidence_fingerprint=evidence_fingerprint,
            output_format=normalized_output_format,
            model=resolved_model,
            provider=resolved_provider,
            base_url=cfg.llm_base_url,
            use_cache=use_cache,
            max_evidence_items=max_evidence_items,
        )
    except (RuntimeError, ValueError, RetryError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if normalized_output_format == "json":
        payload = render_doctor_advice_json(
            advice_markdown,
            assessment=assessment,
            provider=resolved_provider,
            model=resolved_model,
            output_format="json",
            max_evidence_items=max_evidence_items,
            evidence_fingerprint=evidence_fingerprint,
        )
        if output is None:
            typer.echo(payload)
        else:
            _write_output(output, payload)
            console.print(f"[green]Doctor advice JSON:[/green] {output}")
        return

    if output is None:
        typer.echo(advice_markdown)
    else:
        _write_output(output, advice_markdown)
        console.print(f"[green]Doctor advice:[/green] {output}")


def _write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
    from j2py.report import write_dashboard_from_state

    if not output_root.exists():
        console.print(f"[red]Error:[/red] output directory not found: {output_root}")
        raise typer.Exit(code=1)
    if not output_root.is_dir():
        console.print(f"[red]Error:[/red] output path is not a directory: {output_root}")
        raise typer.Exit(code=1)
    state_file = output_root / ".j2py-state.json"
    if not state_file.is_file():
        console.print(f"[red]Error:[/red] state file not found or is not a file: {state_file}")
        raise typer.Exit(code=1)

    dashboard_path = output or output_root / "dashboard.html"
    write_dashboard_from_state(output_root, dashboard_path)
    console.print(f"[green]Dashboard:[/green] {dashboard_path}")


def sarif(
    assessment: Path = typer.Argument(..., help="Doctor assessment JSON to convert."),
    output: Path = typer.Option(..., "--output", "-o", help="SARIF output path."),
) -> None:
    """Export doctor assessment diagnostics as SARIF 2.1.0."""
    from j2py.sarif import assessment_to_sarif, load_sarif_assessment, write_sarif

    try:
        report = assessment_to_sarif(load_sarif_assessment(assessment))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    write_sarif(output, report)
    result_count = len(report.payload["runs"][0]["results"])
    console.print(f"[green]SARIF:[/green] {output} ({result_count} results)")
