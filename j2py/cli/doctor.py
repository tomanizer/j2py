"""Doctor, dashboard, and SARIF CLI adapters."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from j2py.cli.config import load_config
from j2py.cli.output import console


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

    dashboard_path = output or output_root / "dashboard.html"
    write_dashboard_from_state(output_root, dashboard_path)
    console.print(f"[green]Dashboard:[/green] {dashboard_path}")


def doctor(
    ctx: typer.Context,
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
    """Assess a Java project before migration without using live LLM calls."""
    from j2py.doctor import (
        assess_project,
        diff_assessments,
        load_assessment_json,
        render_doctor_diff_text,
        write_assessment_html,
        write_assessment_json,
        write_config_suggestions,
        write_doctor_diff_json,
    )

    if str(source) == "diff":
        if len(ctx.args) != 2:
            console.print("[red]Error:[/red] usage: j2py doctor diff BEFORE_JSON AFTER_JSON")
            raise typer.Exit(code=2)
        if config or html_path is not None or config_suggestions_path is not None:
            console.print(
                "[red]Error:[/red] doctor diff only supports --json output among doctor options"
            )
            raise typer.Exit(code=2)
        try:
            diff = diff_assessments(
                load_assessment_json(Path(ctx.args[0])),
                load_assessment_json(Path(ctx.args[1])),
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        if json_path is not None:
            write_doctor_diff_json(json_path, diff)
            console.print(f"[green]Doctor diff JSON:[/green] {json_path}")
        typer.echo(render_doctor_diff_text(diff), nl=False)
        return

    if ctx.args:
        console.print(f"[red]Error:[/red] unexpected doctor arguments: {' '.join(ctx.args)}")
        raise typer.Exit(code=2)

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
    console.print(
        "[bold]Doctor assessment:[/bold] "
        f"{summary['files']} files, "
        f"{summary['parse_failures']} parse failures, "
        f"{summary['semantic_warnings']} semantic warnings, "
        f"{summary['unhandled_diagnostics']} unhandled diagnostics",
    )


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
