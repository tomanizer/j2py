#!/usr/bin/env python3
"""Run the rule-based skeleton translator against a Spring Framework sample.

This is a non-CI corpus harness. It never calls the LLM layer; it measures how far the
deterministic tree-sitter-based skeleton translator gets on real Spring Java files.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from j2py.analyze.symbols import extract_symbols  # noqa: E402
from j2py.config.loader import ConfigLoader  # noqa: E402
from j2py.parse.java_ast import parse_file  # noqa: E402
from j2py.translate.skeleton import translate_skeleton_with_diagnostics  # noqa: E402

DEFAULT_SPRING_REPO = REPO_ROOT / ".corpus" / "spring-framework"
DEFAULT_JSON_OUT = REPO_ROOT / "corpus-reports" / "spring-sample.json"
DEFAULT_CSV_OUT = REPO_ROOT / "corpus-reports" / "spring-sample.csv"
SPRING_REMOTE = "https://github.com/spring-projects/spring-framework.git"
DEFAULT_MODULES = (
    "spring-core/src/main/java",
    "spring-beans/src/main/java",
)


@dataclass(frozen=True)
class FileMetric:
    path: str
    parse_ok: bool
    parse_error_count: int
    syntax_ok: bool
    coverage: float
    handled_count: int
    unhandled_count: int
    warning_count: int
    unhandled_node_types: str
    unhandled_reasons: str
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure j2py skeleton coverage on a Spring Framework Java sample.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_SPRING_REPO,
        help=f"Spring checkout path. Default: {DEFAULT_SPRING_REPO}",
    )
    parser.add_argument(
        "--clone",
        action="store_true",
        help="Clone Spring Framework into --repo if it is missing.",
    )
    parser.add_argument(
        "--remote",
        default=SPRING_REMOTE,
        help=f"Git remote used with --clone. Default: {SPRING_REMOTE}",
    )
    parser.add_argument(
        "--ref",
        default="main",
        help="Branch/tag/commit to checkout when cloning or refreshing. Default: main",
    )
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help=(
            "Spring-relative source directory to sample. Can be repeated. "
            f"Default: {', '.join(DEFAULT_MODULES)}"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of Java files to translate. Default: 100",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_OUT,
        help=f"Detailed JSON report path. Default: {DEFAULT_JSON_OUT}",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=DEFAULT_CSV_OUT,
        help=f"Per-file CSV report path. Default: {DEFAULT_CSV_OUT}",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include src/test/java trees when --module is not provided.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()

    if args.clone:
        ensure_spring_checkout(repo, remote=args.remote, ref=args.ref)

    if not repo.exists():
        print(
            f"Spring checkout not found at {repo}. Re-run with --clone or pass --repo.",
            file=sys.stderr,
        )
        return 2

    files = collect_java_files(
        repo,
        modules=tuple(args.modules or DEFAULT_MODULES),
        limit=args.limit,
        include_tests=args.include_tests,
    )
    if not files:
        print(f"No Java files found under {repo}", file=sys.stderr)
        return 2

    cfg = ConfigLoader().add_defaults().build()
    metrics = [measure_file(path, repo=repo, cfg=cfg) for path in files]
    summary = summarize(metrics)

    write_json(args.json_out, summary=summary, metrics=metrics)
    write_csv(args.csv_out, metrics)
    print_human_summary(summary, args.json_out, args.csv_out)
    return 0


def ensure_spring_checkout(repo: Path, *, remote: str, ref: str) -> None:
    if repo.exists():
        if not (repo / ".git").exists():
            raise SystemExit(f"{repo} exists but is not a git checkout")
        subprocess.run(["git", "-C", str(repo), "fetch", "--depth", "1", "origin", ref], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "FETCH_HEAD"], check=True)
        return

    repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            ref,
            remote,
            str(repo),
        ],
        check=True,
    )


def collect_java_files(
    repo: Path,
    *,
    modules: tuple[str, ...],
    limit: int,
    include_tests: bool,
) -> list[Path]:
    roots: list[Path] = []
    for module in modules:
        root = repo / module
        if root.exists():
            roots.append(root)

    if not roots:
        roots.extend(sorted(repo.glob("*/src/main/java")))
        if include_tests:
            roots.extend(sorted(repo.glob("*/src/test/java")))

    seen: set[Path] = set()
    files: list[Path] = []
    for root in roots:
        for path in sorted(root.rglob("*.java")):
            if path not in seen:
                seen.add(path)
                files.append(path)

    return files[:limit]


def measure_file(path: Path, *, repo: Path, cfg: Any) -> FileMetric:
    relative = path.relative_to(repo).as_posix()
    try:
        parsed = parse_file(path)
        symbols = extract_symbols(parsed)
        result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)
        syntax_ok = _syntax_ok(result.source)
        unhandled_types = Counter(d.node_type for d in result.diagnostics.unhandled)
        unhandled_reasons = Counter(d.reason for d in result.diagnostics.unhandled)
        return FileMetric(
            path=relative,
            parse_ok=not parsed.has_errors,
            parse_error_count=len(parsed.errors),
            syntax_ok=syntax_ok,
            coverage=result.coverage,
            handled_count=len(result.diagnostics.handled),
            unhandled_count=len(result.diagnostics.unhandled),
            warning_count=len(result.diagnostics.warnings),
            unhandled_node_types=_counter_summary(unhandled_types),
            unhandled_reasons=_counter_summary(unhandled_reasons),
        )
    except Exception as exc:  # noqa: BLE001 - corpus runs should continue past bad files.
        return FileMetric(
            path=relative,
            parse_ok=False,
            parse_error_count=0,
            syntax_ok=False,
            coverage=0.0,
            handled_count=0,
            unhandled_count=1,
            warning_count=0,
            unhandled_node_types="",
            unhandled_reasons="",
            error=f"{type(exc).__name__}: {exc}",
        )


def summarize(metrics: list[FileMetric]) -> dict[str, Any]:
    unhandled_types: Counter[str] = Counter()
    unhandled_reasons: Counter[str] = Counter()
    for metric in metrics:
        unhandled_types.update(_parse_counter_summary(metric.unhandled_node_types))
        unhandled_reasons.update(_parse_counter_summary(metric.unhandled_reasons))

    return {
        "files_scanned": len(metrics),
        "parse_success_rate": _rate(sum(m.parse_ok for m in metrics), len(metrics)),
        "syntax_success_rate": _rate(sum(m.syntax_ok for m in metrics), len(metrics)),
        "average_coverage": mean(m.coverage for m in metrics) if metrics else 0.0,
        "full_coverage_files": sum(m.coverage == 1.0 for m in metrics),
        "files_with_unhandled": sum(m.unhandled_count > 0 for m in metrics),
        "top_unhandled_node_types": unhandled_types.most_common(20),
        "top_unhandled_reasons": unhandled_reasons.most_common(20),
    }


def write_json(path: Path, *, summary: dict[str, Any], metrics: list[FileMetric]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "files": [asdict(metric) for metric in metrics],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, metrics: list[FileMetric]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FileMetric.__dataclass_fields__))
        writer.writeheader()
        for metric in metrics:
            writer.writerow(asdict(metric))


def print_human_summary(summary: dict[str, Any], json_out: Path, csv_out: Path) -> None:
    print(f"Files scanned: {summary['files_scanned']}")
    print(f"Parse success rate: {summary['parse_success_rate']:.2%}")
    print(f"Generated Python syntax success rate: {summary['syntax_success_rate']:.2%}")
    print(f"Average skeleton coverage: {summary['average_coverage']:.2%}")
    print(f"Full-coverage files: {summary['full_coverage_files']}")
    print(f"Files with unhandled constructs: {summary['files_with_unhandled']}")
    print(f"JSON report: {json_out}")
    print(f"CSV report: {csv_out}")


def _syntax_ok(source: str) -> bool:
    try:
        ast.parse(source)
    except SyntaxError:
        return False
    return True


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _counter_summary(counter: Counter[str]) -> str:
    return ";".join(f"{key}:{value}" for key, value in sorted(counter.items()))


def _parse_counter_summary(value: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not value:
        return counter
    for part in value.split(";"):
        key, raw_count = part.rsplit(":", 1)
        counter[key] = int(raw_count)
    return counter


if __name__ == "__main__":
    raise SystemExit(main())
