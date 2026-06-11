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
import re
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
DEFAULT_BASELINE = REPO_ROOT / "tests" / "fixtures" / "corpus" / "spring-sample-baseline.json"
SPRING_REMOTE = "https://github.com/spring-projects/spring-framework.git"
SPRING_REF = "0c60266986197a191ff33eb498ebc8bac3dc933f"
DEFAULT_LIMIT = 100
SMOKE_LIMIT = 25
COVERAGE_THRESHOLD = 0.80
DEFAULT_MODULES = (
    "spring-core/src/main/java",
    "spring-beans/src/main/java",
)

# Curated minimal, dense construct examples (for broad coverage of specific Java features used in Spring).
# These are small files targeting things like interface defaults, text blocks, anonymous classes,
# switch fall-through, advanced enums, etc. They can be mixed in for "construct coverage" runs.
CONSTRUCTS_DIR = REPO_ROOT / "tests" / "fixtures" / "corpus" / "constructs"


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
        default=SPRING_REF,
        help=f"Branch/tag/commit to checkout when cloning or refreshing. Default: {SPRING_REF}",
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
        default=DEFAULT_LIMIT,
        help=f"Maximum number of Java files to translate. Default: {DEFAULT_LIMIT}",
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
    parser.add_argument(
        "--strategy",
        choices=["lexical", "random", "density"],
        default="lexical",
        help=(
            "File selection strategy. 'density' scores files by (distinct AST node types / size) "
            "and prefers small but construct-rich files. 'random' uses a fixed seed for reproducibility."
        ),
    )
    parser.add_argument(
        "--max-loc",
        type=int,
        default=0,
        help="Maximum source lines per file (0 = unlimited). Encourages minimal-size test files.",
    )
    parser.add_argument(
        "--min-constructs",
        type=int,
        default=0,
        help="Minimum number of (handled + unhandled) constructs for a file to be considered (0 = no filter).",
    )
    parser.add_argument(
        "--include-constructs",
        action="store_true",
        help="Include (and prioritize) curated minimal construct files from tests/fixtures/corpus/constructs/. "
             "Useful for ensuring broad coverage of specific Spring-used Java features.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help=f"Baseline JSON path for compare/update modes. Default: {DEFAULT_BASELINE}",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare the current summary with --baseline and print deltas.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite --baseline with the current summary and run metadata.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when --compare-baseline detects a regression.",
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
        strategy=args.strategy,
        max_loc=args.max_loc,
        min_constructs=args.min_constructs,
        include_constructs=args.include_constructs,
    )
    if not files:
        print(f"No Java files found under {repo}", file=sys.stderr)
        return 2

    cfg = ConfigLoader().add_defaults().build()
    metrics = [measure_file(path, repo=repo, cfg=cfg) for path in files]
    summary = summarize(metrics)
    metadata = build_metadata(
        repo=repo,
        requested_ref=args.ref,
        modules=tuple(args.modules or DEFAULT_MODULES),
        limit=args.limit,
        include_tests=args.include_tests,
        strategy=args.strategy,
        max_loc=args.max_loc,
        min_constructs=args.min_constructs,
        include_constructs=args.include_constructs,
    )

    write_json(args.json_out, metadata=metadata, summary=summary, metrics=metrics)
    write_csv(args.csv_out, metrics)
    print_human_summary(summary, args.json_out, args.csv_out)

    comparison: dict[str, Any] | None = None
    if args.update_baseline:
        write_baseline(args.baseline, metadata=metadata, summary=summary, metrics=metrics)
        print(f"Baseline updated: {args.baseline}")

    if args.compare_baseline:
        comparison = compare_baseline(
            args.baseline,
            metadata=metadata,
            summary=summary,
            metrics=metrics,
        )
        print_comparison(comparison)

    if (
        args.fail_on_regression
        and comparison
        and (comparison["regressions"] or _has_file_regressions(comparison["file_regressions"]))
    ):
        return 1
    return 0


def ensure_spring_checkout(repo: Path, *, remote: str, ref: str) -> None:
    if repo.exists():
        if not (repo / ".git").exists():
            raise SystemExit(f"{repo} exists but is not a git checkout")
        subprocess.run(["git", "-C", str(repo), "fetch", "--depth", "1", "origin", ref], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "FETCH_HEAD"], check=True)
        return

    repo.parent.mkdir(parents=True, exist_ok=True)
    if _looks_like_commit_sha(ref):
        subprocess.run(["git", "clone", "--depth", "1", remote, str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "fetch", "--depth", "1", "origin", ref], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "FETCH_HEAD"], check=True)
        return

    subprocess.run(["git", "clone", "--depth", "1", "--branch", ref, remote, str(repo)], check=True)


def collect_java_files(
    repo: Path,
    *,
    modules: tuple[str, ...],
    limit: int,
    include_tests: bool,
    strategy: str = "lexical",
    max_loc: int = 0,
    min_constructs: int = 0,
    include_constructs: bool = False,
) -> list[Path]:
    """Collect Java files with improved strategies for minimal size + broad construct coverage.

    Strategies:
    - lexical: original deterministic order (for stable baselines)
    - random: shuffled with fixed seed (reproducible)
    - density: prefer small files with high ratio of distinct tree-sitter Java node types.
      Combined with max_loc / min_constructs this produces the "minimal but rich" files the user wants.
    """
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
    candidates: list[Path] = []
    for root in roots:
        for path in sorted(root.rglob("*.java")):
            if path not in seen:
                seen.add(path)
                candidates.append(path)

    # Optionally mix in curated minimal construct examples (very small, high signal files)
    if include_constructs and CONSTRUCTS_DIR.exists():
        for path in sorted(CONSTRUCTS_DIR.glob("*.java")):
            if path not in seen:
                seen.add(path)
                candidates.append(path)

    # Apply size / density filters (these enforce "minimal size" while keeping breadth)
    filtered: list[tuple[Path, int, int]] = []  # (path, loc, construct_count)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            loc = len(text.splitlines())
            if max_loc > 0 and loc > max_loc:
                continue
            # Quick parse to count constructs (distinct node types + total handled/unhandled proxy)
            parsed = parse_file(path)  # cheap enough for corpus runs
            node_types = {n.type for n in parsed.root.walk()}
            # Rough construct count: number of interesting nodes (decls, stmts, exprs)
            construct_count = len(node_types)
            if min_constructs > 0 and construct_count < min_constructs:
                continue
            filtered.append((path, loc, construct_count))
        except Exception:
            # Skip unparsable for selection purposes; measure_file will still report them
            if min_constructs == 0:
                filtered.append((path, 999999, 0))

    if not filtered:
        return []

    if strategy == "random":
        import random
        random.seed(42)  # fixed for reproducibility across runs
        random.shuffle(filtered)
        selected = [p for p, _, _ in filtered[:limit]]
    elif strategy == "density":
        # Density = distinct node types / LOC (higher is better for "broad coverage in minimal size")
        scored = []
        for p, loc, cnt in filtered:
            density = cnt / max(1, loc)
            scored.append((density, -loc, p))  # prefer high density, then smaller files
        scored.sort(reverse=True)
        selected = [p for _, _, p in scored[:limit]]
    else:
        # lexical (default, stable for baselines)
        selected = [p for p, _, _ in sorted(filtered)[:limit]]

    return selected


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

    coverage_metrics = [
        metric for metric in metrics if metric.handled_count + metric.unhandled_count > 0
    ]

    return {
        "files_scanned": len(metrics),
        "parse_success_rate": _rate(sum(m.parse_ok for m in metrics), len(metrics)),
        "syntax_success_rate": _rate(sum(m.syntax_ok for m in metrics), len(metrics)),
        "coverage_file_count": len(coverage_metrics),
        "average_coverage": (
            mean(m.coverage for m in coverage_metrics) if coverage_metrics else 0.0
        ),
        "full_coverage_files": sum(m.coverage == 1.0 for m in coverage_metrics),
        "files_with_unhandled": sum(m.unhandled_count > 0 for m in metrics),
        "coverage_threshold": COVERAGE_THRESHOLD,
        "files_below_coverage_threshold": sum(
            m.coverage < COVERAGE_THRESHOLD for m in coverage_metrics
        ),
        "top_unhandled_node_types": unhandled_types.most_common(20),
        "top_unhandled_reasons": unhandled_reasons.most_common(20),
    }


def build_metadata(
    *,
    repo: Path,
    requested_ref: str,
    modules: tuple[str, ...],
    limit: int,
    include_tests: bool,
    strategy: str = "lexical",
    max_loc: int = 0,
    min_constructs: int = 0,
    include_constructs: bool = False,
) -> dict[str, Any]:
    return {
        "spring_remote": SPRING_REMOTE,
        "spring_ref": requested_ref,
        "spring_checkout": _git_head(repo),
        "modules": list(modules),
        "limit": limit,
        "include_tests": include_tests,
        "strategy": strategy,
        "max_loc": max_loc,
        "min_constructs": min_constructs,
        "include_constructs": include_constructs,
    }


def write_json(
    path: Path,
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: list[FileMetric],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": metadata,
        "summary": summary,
        "files": [asdict(metric) for metric in metrics],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_baseline(
    path: Path,
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: list[FileMetric],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": metadata,
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
    print(f"Files included in coverage metrics: {summary['coverage_file_count']}")
    print(f"Parse success rate: {summary['parse_success_rate']:.2%}")
    print(f"Generated Python syntax success rate: {summary['syntax_success_rate']:.2%}")
    print(f"Average skeleton coverage: {summary['average_coverage']:.2%}")
    print(f"Full-coverage files: {summary['full_coverage_files']}")
    print(f"Files with unhandled constructs: {summary['files_with_unhandled']}")
    print(
        "Files below "
        f"{summary['coverage_threshold']:.0%} coverage: "
        f"{summary['files_below_coverage_threshold']}"
    )
    print(f"JSON report: {json_out}")
    print(f"CSV report: {csv_out}")


def compare_baseline(
    path: Path,
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: list[FileMetric],
) -> dict[str, Any]:
    baseline = json.loads(path.read_text())
    baseline_summary = baseline["summary"]
    baseline_metadata = baseline.get("metadata", {})

    metric_specs = {
        "parse_success_rate": "higher",
        "syntax_success_rate": "higher",
        "average_coverage": "higher",
        "full_coverage_files": "higher",
        "files_with_unhandled": "lower",
        "files_below_coverage_threshold": "lower",
    }
    deltas: dict[str, dict[str, Any]] = {}
    regressions: list[str] = []
    improvements: list[str] = []
    for metric, direction in metric_specs.items():
        baseline_value = baseline_summary[metric]
        current_value = summary[metric]
        delta = current_value - baseline_value
        deltas[metric] = {
            "baseline": baseline_value,
            "current": current_value,
            "delta": delta,
            "direction": direction,
        }
        if _is_regression(delta, direction):
            regressions.append(metric)
        elif _is_improvement(delta, direction):
            improvements.append(metric)

    metadata_mismatches = [
        key
        for key in (
            "spring_ref",
            "modules",
            "limit",
            "include_tests",
            "strategy",
            "max_loc",
            "min_constructs",
            "include_constructs",
        )
        if baseline_metadata.get(key) != metadata.get(key)
    ]

    return {
        "baseline_path": str(path),
        "deltas": deltas,
        "improvements": improvements,
        "regressions": regressions,
        "metadata_mismatches": metadata_mismatches,
        "file_regressions": _file_regressions(
            baseline.get("files", []),
            [asdict(metric) for metric in metrics],
        ),
        "baseline_top_unhandled_node_types": baseline_summary["top_unhandled_node_types"],
        "current_top_unhandled_node_types": summary["top_unhandled_node_types"],
        "baseline_top_unhandled_reasons": baseline_summary["top_unhandled_reasons"],
        "current_top_unhandled_reasons": summary["top_unhandled_reasons"],
    }


def print_comparison(comparison: dict[str, Any]) -> None:
    print(f"Baseline comparison: {comparison['baseline_path']}")
    for metric, values in comparison["deltas"].items():
        print(
            f"  {metric}: {_format_metric(values['baseline'])} -> "
            f"{_format_metric(values['current'])} ({_format_delta(values['delta'])})"
        )
    if comparison["metadata_mismatches"]:
        print(f"Metadata mismatch: {', '.join(comparison['metadata_mismatches'])}")
    if comparison["improvements"]:
        print(f"Improvements: {', '.join(comparison['improvements'])}")
    if comparison["regressions"]:
        print(f"Regressions: {', '.join(comparison['regressions'])}")
    else:
        print("Regressions: none")
    print("Top unhandled node types:")
    print(f"  baseline: {_top_list(comparison['baseline_top_unhandled_node_types'])}")
    print(f"  current:  {_top_list(comparison['current_top_unhandled_node_types'])}")
    _print_file_regressions(comparison["file_regressions"])


def _file_regressions(
    baseline_files: list[dict[str, Any]],
    current_files: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    baseline_by_path = {item["path"]: item for item in baseline_files}
    current_by_path = {item["path"]: item for item in current_files}

    parse_failures: list[dict[str, Any]] = []
    syntax_failures: list[dict[str, Any]] = []
    coverage_drops: list[dict[str, Any]] = []
    unhandled_increases: list[dict[str, Any]] = []
    new_unhandled_reasons: list[dict[str, Any]] = []

    for path, current in current_by_path.items():
        baseline = baseline_by_path.get(path)
        if baseline is None:
            continue
        if baseline.get("parse_ok") and not current.get("parse_ok"):
            parse_failures.append({"path": path, "error": current.get("error", "")})
        if baseline.get("syntax_ok") and not current.get("syntax_ok"):
            syntax_failures.append({"path": path, "error": current.get("error", "")})

        coverage_delta = current["coverage"] - baseline["coverage"]
        if coverage_delta < -1e-12:
            coverage_drops.append(
                {
                    "path": path,
                    "baseline": baseline["coverage"],
                    "current": current["coverage"],
                    "delta": coverage_delta,
                },
            )

        unhandled_delta = current["unhandled_count"] - baseline["unhandled_count"]
        if unhandled_delta > 0:
            unhandled_increases.append(
                {
                    "path": path,
                    "baseline": baseline["unhandled_count"],
                    "current": current["unhandled_count"],
                    "delta": unhandled_delta,
                },
            )

        baseline_reasons = _parse_counter_summary(baseline.get("unhandled_reasons", ""))
        current_reasons = _parse_counter_summary(current.get("unhandled_reasons", ""))
        for reason, count in sorted(current_reasons.items()):
            delta = count - baseline_reasons.get(reason, 0)
            if delta > 0:
                new_unhandled_reasons.append(
                    {
                        "path": path,
                        "reason": reason,
                        "baseline": baseline_reasons.get(reason, 0),
                        "current": count,
                        "delta": delta,
                    },
                )

    return {
        "parse_failures": parse_failures,
        "syntax_failures": syntax_failures,
        "coverage_drops": coverage_drops,
        "unhandled_increases": unhandled_increases,
        "new_unhandled_reasons": new_unhandled_reasons,
    }


def _print_file_regressions(file_regressions: dict[str, list[dict[str, Any]]]) -> None:
    if not any(file_regressions.values()):
        print("Per-file regressions: none")
        return

    print("Per-file regressions:")
    labels = {
        "parse_failures": "new parse failures",
        "syntax_failures": "new syntax failures",
        "coverage_drops": "coverage drops",
        "unhandled_increases": "unhandled count increases",
        "new_unhandled_reasons": "new unhandled reasons",
    }
    for key, label in labels.items():
        items = file_regressions[key]
        if not items:
            continue
        print(f"  {label}: {len(items)}")
        for item in items[:5]:
            detail = item.get("reason") or _format_delta(item.get("delta", 0))
            print(f"    - {item['path']}: {detail}")


def _has_file_regressions(file_regressions: dict[str, list[dict[str, Any]]]) -> bool:
    return any(file_regressions.values())


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


def _looks_like_commit_sha(ref: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{40}", ref))


def _git_head(repo: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return ""
    return proc.stdout.strip()


def _is_regression(delta: float | int, direction: str) -> bool:
    if direction == "higher":
        return delta < -1e-12
    return delta > 1e-12


def _is_improvement(delta: float | int, direction: str) -> bool:
    if direction == "higher":
        return delta > 1e-12
    return delta < -1e-12


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2%}"
    return str(value)


def _format_delta(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:+.2%}"
    return f"{value:+}"


def _top_list(values: list[list[Any]] | list[tuple[Any, ...]], *, limit: int = 5) -> str:
    return ", ".join(f"{name}:{count}" for name, count in values[:limit])


if __name__ == "__main__":
    raise SystemExit(main())
