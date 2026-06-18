#!/usr/bin/env python3
"""Run the rule-based skeleton translator against external Java corpora.

This is a non-CI corpus harness. It never calls the LLM layer; it measures how far the
deterministic tree-sitter-based skeleton translator gets on real Java source samples.

Use ``--preset`` for pinned corpora (Guava, Commons Lang, Jackson, Caffeine, Spring,
etc.) — see ``scripts/corpus/corpus_presets.py`` or ``--list-presets``. Bare
invocations keep the historical Spring lexical defaults for compatibility.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
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

_CORPUS_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_CORPUS_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_CORPUS_SCRIPT_DIR))

from corpus_presets import (  # noqa: E402, I001
    apply_preset,
    corpus_checkout_root,
    get_preset,
    list_preset_names,
)
from annotation_filter import (  # noqa: E402
    DEFAULT_ENTERPRISE_ANNOTATIONS as _DEFAULT_ANNOTATIONS,
    annotation_family_file_counts,
    passes_annotation_filter,
)
from enterprise_metrics import (  # noqa: E402
    file_enterprise_signals,
    summarize_enterprise,
)
from baseline_comparison import (  # noqa: E402
    compare_baseline,
    has_file_regressions as _has_file_regressions,
    print_comparison,
)
from counter_summary import (  # noqa: E402
    counter_summary as _counter_summary,
    parse_counter_summary as _parse_counter_summary,
)
from report_io import write_csv_report, write_json_report  # noqa: E402

LEGACY_DEFAULT_REPO = corpus_checkout_root() / "spring-framework"
LEGACY_DEFAULT_JSON_OUT = REPO_ROOT / "corpus-reports" / "spring-sample.json"
LEGACY_DEFAULT_CSV_OUT = REPO_ROOT / "corpus-reports" / "spring-sample.csv"
LEGACY_DEFAULT_BASELINE = (
    REPO_ROOT / "tests" / "fixtures" / "corpus" / "spring-sample-baseline.json"
)
LEGACY_DEFAULT_REMOTE = "https://github.com/spring-projects/spring-framework.git"
LEGACY_DEFAULT_REF = "0c60266986197a191ff33eb498ebc8bac3dc933f"
DEFAULT_LIMIT = 200
SMOKE_LIMIT = 25
COVERAGE_THRESHOLD = 0.80
LEGACY_DEFAULT_MODULES = (
    "spring-core/src/main/java",
    "spring-beans/src/main/java",
)

# Curated minimal, dense construct examples for broad Java feature coverage.
# These are small files targeting things like interface defaults, text blocks, anonymous classes,
# switch fall-through, advanced enums, etc. They can be mixed in for "construct coverage" runs.
CONSTRUCTS_DIR = REPO_ROOT / "tests" / "fixtures" / "corpus" / "constructs"


def is_package_info_path(path: Path) -> bool:
    """Return True for Java package descriptor files (no real class body to translate)."""
    return path.name == "package-info.java"


def matches_path_prefix(relative_path: str, prefixes: tuple[str, ...]) -> bool:
    """Return True when ``relative_path`` starts with any pinned corpus prefix."""
    return any(relative_path.startswith(prefix) for prefix in prefixes)


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
    method_body_count: int = 0
    annotation_use_count: int = 0
    annotation_warning_count: int = 0
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure j2py skeleton coverage on an external Java corpus sample.",
    )
    parser.add_argument(
        "--preset",
        choices=list_preset_names(),
        help="Use a pinned corpus preset (remote, ref, modules, baseline, sampling).",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="Print available corpus presets and exit.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help=(
            "Corpus checkout path. Defaults to the preset checkout under "
            "$J2PY_CORPUS_ROOT/.corpus or .corpus; bare legacy runs default to "
            "the spring-framework checkout."
        ),
    )
    parser.add_argument(
        "--clone",
        action="store_true",
        help="Clone the corpus remote into --repo if it is missing.",
    )
    parser.add_argument(
        "--remote",
        default=None,
        help="Git remote used with --clone.",
    )
    parser.add_argument(
        "--ref",
        default=None,
        help="Branch/tag/commit to checkout when cloning or refreshing.",
    )
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help=(
            "Corpus checkout-relative source directory to sample. Can be repeated. "
            f"Legacy default: {', '.join(LEGACY_DEFAULT_MODULES)}"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"Maximum number of Java files to translate. Default: {DEFAULT_LIMIT}",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help=f"Detailed JSON report path. Legacy default: {LEGACY_DEFAULT_JSON_OUT}",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help=f"Per-file CSV report path. Legacy default: {LEGACY_DEFAULT_CSV_OUT}",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include src/test/java trees when --module is not provided.",
    )
    parser.add_argument(
        "--strategy",
        choices=["lexical", "random", "density"],
        default=None,
        help=(
            "File selection strategy. 'density' scores files by (distinct AST node types / size) "
            "and prefers small but construct-rich files. 'random' uses a fixed seed for "
            "reproducibility."
        ),
    )
    parser.add_argument(
        "--max-loc",
        type=int,
        default=None,
        help="Maximum source lines per file (0 = unlimited). Encourages minimal-size test files.",
    )
    parser.add_argument(
        "--min-loc",
        type=int,
        default=None,
        help=(
            "Minimum source lines per file (0 = no floor). Excludes trivial one-liner stubs "
            "from density sampling."
        ),
    )
    parser.add_argument(
        "--min-constructs",
        type=int,
        default=None,
        help=(
            "Minimum number of (handled + unhandled) constructs for a file to be considered "
            "(0 = no filter)."
        ),
    )
    parser.add_argument(
        "--include-constructs",
        action="store_true",
        help=(
            "Include (and prioritize) curated minimal construct files from "
            "tests/fixtures/corpus/constructs/. Useful for ensuring broad coverage of "
            "specific Java features."
        ),
    )
    parser.add_argument(
        "--include-package-info",
        action="store_true",
        help=(
            "Include package-info.java files in the sample. By default these package "
            "descriptors are excluded so the corpus measures real class sources."
        ),
    )
    parser.add_argument(
        "--require-annotation",
        action="append",
        dest="require_annotations",
        default=None,
        help=(
            "Annotation simple name that must appear as @Name in a file (repeatable). "
            "Used with --min-annotation-hits for enterprise Spring sampling."
        ),
    )
    parser.add_argument(
        "--min-annotation-hits",
        type=int,
        default=None,
        help=(
            "Minimum total @annotation occurrences from --require-annotation names "
            "(0 = no annotation filter)."
        ),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=(
            "Baseline JSON path for compare/update modes. "
            f"Legacy default: {LEGACY_DEFAULT_BASELINE}"
        ),
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


def resolve_args(args: argparse.Namespace) -> argparse.Namespace:
    """Apply preset defaults, then legacy Spring defaults for bare invocations."""
    if args.list_presets:
        return args

    raw = {
        "repo": args.repo,
        "remote": args.remote,
        "ref": args.ref,
        "modules": args.modules,
        "limit": args.limit,
        "strategy": args.strategy,
        "max_loc": args.max_loc,
        "min_loc": args.min_loc,
        "min_constructs": args.min_constructs,
        "include_constructs": True if args.include_constructs else None,
        "include_tests": True if args.include_tests else None,
        "skip_package_info": False if args.include_package_info else None,
        "exclude_paths": None,
        "include_path_prefixes": None,
        "require_annotations": None,
        "min_annotation_hits": None,
        "baseline": args.baseline,
        "json_out": args.json_out,
        "csv_out": args.csv_out,
    }

    if args.preset:
        resolved = apply_preset(get_preset(args.preset), raw)
        if raw["require_annotations"] is not None:
            resolved["require_annotations"] = raw["require_annotations"]
        if raw["min_annotation_hits"] is not None:
            resolved["min_annotation_hits"] = raw["min_annotation_hits"]
    else:
        resolved = {
            **raw,
            "repo": raw["repo"] or LEGACY_DEFAULT_REPO,
            "remote": raw["remote"] or LEGACY_DEFAULT_REMOTE,
            "ref": raw["ref"] or LEGACY_DEFAULT_REF,
            "modules": raw["modules"] or list(LEGACY_DEFAULT_MODULES),
            "limit": raw["limit"] if raw["limit"] is not None else DEFAULT_LIMIT,
            "strategy": raw["strategy"] or "lexical",
            "max_loc": raw["max_loc"] if raw["max_loc"] is not None else 0,
            "min_loc": raw["min_loc"] if raw["min_loc"] is not None else 0,
            "min_constructs": raw["min_constructs"] if raw["min_constructs"] is not None else 0,
            "include_constructs": bool(raw["include_constructs"]),
            "include_tests": bool(raw["include_tests"]),
            "skip_package_info": (
                raw["skip_package_info"] if raw["skip_package_info"] is not None else True
            ),
            "exclude_paths": [],
            "include_path_prefixes": [],
            "require_annotations": [],
            "min_annotation_hits": 0,
            "baseline": raw["baseline"] or LEGACY_DEFAULT_BASELINE,
            "json_out": raw["json_out"] or LEGACY_DEFAULT_JSON_OUT,
            "csv_out": raw["csv_out"] or LEGACY_DEFAULT_CSV_OUT,
            "preset": None,
        }

    args.repo = resolved["repo"]
    args.remote = resolved["remote"]
    args.ref = resolved["ref"]
    args.modules = resolved["modules"]
    args.limit = resolved["limit"]
    args.strategy = resolved["strategy"]
    args.max_loc = resolved["max_loc"]
    args.min_loc = resolved["min_loc"]
    args.min_constructs = resolved["min_constructs"]
    args.include_constructs = resolved["include_constructs"]
    args.include_tests = resolved["include_tests"]
    args.skip_package_info = resolved["skip_package_info"]
    args.exclude_paths = tuple(resolved["exclude_paths"])
    args.include_path_prefixes = tuple(resolved["include_path_prefixes"])
    args.require_annotations = tuple(resolved["require_annotations"])
    args.min_annotation_hits = resolved["min_annotation_hits"]
    args.baseline = resolved["baseline"]
    args.json_out = resolved["json_out"]
    args.csv_out = resolved["csv_out"]
    args.preset_name = resolved.get("preset")
    return args


def print_preset_catalog() -> None:
    for name in list_preset_names():
        preset = get_preset(name)
        print(f"{name}\t{preset.description}")


def main() -> int:
    args = resolve_args(parse_args())
    if args.list_presets:
        print_preset_catalog()
        return 0

    if args.compare_baseline and not args.update_baseline and not args.baseline.exists():
        print(
            f"Baseline file not found: {args.baseline}. "
            "Run with --update-baseline first to create it.",
            file=sys.stderr,
        )
        return 2

    repo = args.repo.resolve()

    if args.clone:
        ensure_repo_checkout(repo, remote=args.remote, ref=args.ref)

    if not repo.exists():
        from corpus_presets import corpus_checkout_root

        root = corpus_checkout_root()
        print(
            f"Corpus checkout not found at {repo}.",
            file=sys.stderr,
        )
        print(
            "Run `make corpus-clone-all`, re-run with --clone, pass --repo, or set "
            f"J2PY_CORPUS_ROOT to a checkout whose `.corpus/` contains the clone "
            f"(current corpus root: {root}).",
            file=sys.stderr,
        )
        return 2

    modules = tuple(args.modules)
    exclude_paths = tuple(args.exclude_paths)
    include_path_prefixes = tuple(args.include_path_prefixes)
    require_annotations = tuple(args.require_annotations)
    min_annotation_hits = args.min_annotation_hits
    files = collect_java_files(
        repo,
        modules=modules,
        limit=args.limit,
        include_tests=args.include_tests,
        strategy=args.strategy,
        max_loc=args.max_loc,
        min_loc=args.min_loc,
        min_constructs=args.min_constructs,
        include_constructs=args.include_constructs,
        skip_package_info=args.skip_package_info,
        exclude_paths=exclude_paths,
        include_path_prefixes=include_path_prefixes,
        require_annotations=require_annotations,
        min_annotation_hits=min_annotation_hits,
    )
    if not files:
        print(f"No Java files found under {repo}", file=sys.stderr)
        return 2

    cfg = ConfigLoader().add_defaults().build()
    metrics = [
        measure_file(
            path,
            repo=repo,
            cfg=cfg,
            annotation_names=require_annotations or _DEFAULT_ANNOTATIONS,
        )
        for path in files
    ]
    summary = summarize(metrics)
    annotation_counts = _annotation_family_counts_for_sample(
        repo,
        files,
        require_annotations=require_annotations,
    )
    metadata = build_metadata(
        repo=repo,
        preset=args.preset_name,
        remote=args.remote,
        requested_ref=args.ref,
        modules=modules,
        limit=args.limit,
        include_tests=args.include_tests,
        strategy=args.strategy,
        max_loc=args.max_loc,
        min_loc=args.min_loc,
        min_constructs=args.min_constructs,
        include_constructs=args.include_constructs,
        skip_package_info=args.skip_package_info,
        exclude_paths=exclude_paths,
        include_path_prefixes=include_path_prefixes,
        require_annotations=require_annotations,
        min_annotation_hits=min_annotation_hits,
        annotation_family_file_counts=annotation_counts,
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


def ensure_repo_checkout(repo: Path, *, remote: str, ref: str) -> None:
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
    min_loc: int = 0,
    min_constructs: int = 0,
    include_constructs: bool = False,
    skip_package_info: bool = True,
    exclude_paths: tuple[str, ...] = (),
    include_path_prefixes: tuple[str, ...] = (),
    require_annotations: tuple[str, ...] = (),
    min_annotation_hits: int = 0,
) -> list[Path]:
    """Collect Java files with improved strategies for minimal size + broad construct coverage.

    Strategies:
    - lexical: original deterministic order (for stable baselines)
    - random: shuffled with fixed seed (reproducible)
    - density: prefer small files with high ratio of distinct tree-sitter Java node types.
      Combined with max_loc / min_loc / min_constructs this produces construct-rich files
      without trivial stubs or oversized sources.
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
    excluded = set(exclude_paths)
    for root in roots:
        for path in sorted(root.rglob("*.java")):
            if path not in seen:
                if skip_package_info and is_package_info_path(path):
                    continue
                rel = path.relative_to(repo).as_posix()
                if rel in excluded:
                    continue
                seen.add(path)
                candidates.append(path)

    construct_paths: list[Path] = []
    # Optionally mix in curated minimal construct examples (very small, high signal files)
    if include_constructs and CONSTRUCTS_DIR.exists():
        for path in sorted(CONSTRUCTS_DIR.glob("*.java")):
            if path not in seen:
                seen.add(path)
                construct_paths.append(path)
                candidates.append(path)
    construct_set = set(construct_paths)
    pinned_prefix_set: set[Path] = set()
    if include_path_prefixes:
        for path in candidates:
            if path in construct_set:
                continue
            try:
                relative = path.relative_to(repo).as_posix()
            except ValueError:
                continue
            if matches_path_prefix(relative, include_path_prefixes):
                pinned_prefix_set.add(path)
    priority_set = construct_set | pinned_prefix_set

    if require_annotations and min_annotation_hits > 0:
        annotation_filtered: list[Path] = []
        for path in candidates:
            if path in priority_set:
                annotation_filtered.append(path)
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if passes_annotation_filter(
                text,
                require_annotations=require_annotations,
                min_annotation_hits=min_annotation_hits,
            ):
                annotation_filtered.append(path)
        candidates = annotation_filtered

    # Apply size / density filters (these enforce "minimal size" while keeping breadth)
    filtered: list[tuple[Path, int, int]] = []  # (path, loc, construct_count)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            loc = len(text.splitlines())
            is_priority = path in priority_set
            if not is_priority and max_loc > 0 and loc > max_loc:
                continue
            if not is_priority and min_loc > 0 and loc < min_loc:
                continue
            # Quick parse to count constructs (distinct node types + total handled/unhandled proxy)
            parsed = parse_file(path)  # cheap enough for corpus runs
            node_types = {n.type for n in parsed.root.walk()}
            # Rough construct count: number of interesting nodes (decls, stmts, exprs)
            construct_count = len(node_types)
            if not is_priority and min_constructs > 0 and construct_count < min_constructs:
                continue
            filtered.append((path, loc, construct_count))
        except Exception:
            # Skip unparsable for selection purposes; measure_file will still report them
            if min_constructs == 0 or path in priority_set:
                filtered.append((path, 999999, 0))

    if not filtered:
        return []

    if priority_set:
        selected: list[Path] = []
        for path in sorted(p for p, _, _ in filtered if p in construct_set):
            selected.append(path)
        for path in sorted(p for p, _, _ in filtered if p in pinned_prefix_set):
            if path not in selected:
                selected.append(path)
        if len(selected) >= limit:
            return selected[:limit]
        selected.extend(
            _select_files(
                [item for item in filtered if item[0] not in set(selected)],
                strategy=strategy,
                limit=limit - len(selected),
            ),
        )
        return selected

    return _select_files(filtered, strategy=strategy, limit=limit)


def _select_files(
    filtered: list[tuple[Path, int, int]],
    *,
    strategy: str,
    limit: int,
) -> list[Path]:
    if limit <= 0:
        return []

    if strategy == "random":
        import random

        random.seed(42)  # fixed for reproducibility across runs
        random.shuffle(filtered)
        selected = [p for p, _, _ in filtered[:limit]]
    elif strategy == "density":
        # Density = distinct node types / LOC, preferring broad coverage in minimal size.
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


def measure_file(
    path: Path,
    *,
    repo: Path,
    cfg: Any,
    annotation_names: tuple[str, ...] = _DEFAULT_ANNOTATIONS,
) -> FileMetric:
    try:
        relative = path.relative_to(repo).as_posix()
    except ValueError:
        # Path is not under the Spring checkout, e.g. curated j2py construct files.
        # Fall back to a path relative to the j2py root for reporting.
        if path.is_relative_to(REPO_ROOT):
            relative = path.relative_to(REPO_ROOT).as_posix()
        else:
            relative = path.as_posix()
    try:
        source_text = path.read_text(encoding="utf-8", errors="ignore")
        parsed = parse_file(path)
        symbols = extract_symbols(parsed)
        result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)
        syntax_ok = _syntax_ok(result.source)
        unhandled_types = Counter(d.node_type for d in result.diagnostics.unhandled)
        unhandled_reasons = Counter(d.reason for d in result.diagnostics.unhandled)
        enterprise = file_enterprise_signals(
            parsed=parsed,
            source_text=source_text,
            warnings=result.diagnostics.warnings,
            annotation_names=annotation_names,
        )
        return FileMetric(
            path=relative,
            parse_ok=not parsed.has_errors,
            parse_error_count=len(parsed.errors),
            syntax_ok=syntax_ok,
            coverage=result.coverage,
            handled_count=len(result.diagnostics.handled),
            unhandled_count=len(result.diagnostics.unhandled),
            warning_count=len(result.diagnostics.warnings),
            method_body_count=enterprise.method_body_count,
            annotation_use_count=enterprise.annotation_use_count,
            annotation_warning_count=enterprise.annotation_warning_count,
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
        "enterprise": summarize_enterprise(metrics),
    }


def build_metadata(
    *,
    repo: Path,
    preset: str | None,
    remote: str,
    requested_ref: str,
    modules: tuple[str, ...],
    limit: int,
    include_tests: bool,
    strategy: str = "lexical",
    max_loc: int = 0,
    min_loc: int = 0,
    min_constructs: int = 0,
    include_constructs: bool = False,
    skip_package_info: bool = True,
    exclude_paths: tuple[str, ...] = (),
    include_path_prefixes: tuple[str, ...] = (),
    require_annotations: tuple[str, ...] = (),
    min_annotation_hits: int = 0,
    annotation_family_file_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    checkout = _git_head(repo)
    metadata: dict[str, Any] = {
        "preset": preset,
        "corpus_remote": remote,
        "corpus_ref": requested_ref,
        "corpus_checkout": checkout,
        "modules": list(modules),
        "limit": limit,
        "include_tests": include_tests,
        "strategy": strategy,
        "max_loc": max_loc,
        "min_loc": min_loc,
        "min_constructs": min_constructs,
        "include_constructs": include_constructs,
        "skip_package_info": skip_package_info,
        "exclude_paths": list(exclude_paths),
        "include_path_prefixes": list(include_path_prefixes),
        "require_annotations": list(require_annotations),
        "min_annotation_hits": min_annotation_hits,
    }
    if require_annotations and annotation_family_file_counts is not None:
        metadata["annotation_family_file_counts"] = annotation_family_file_counts
    if remote == LEGACY_DEFAULT_REMOTE:
        metadata["spring_remote"] = remote
        metadata["spring_ref"] = requested_ref
        metadata["spring_checkout"] = checkout
    return metadata


def write_json(
    path: Path,
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: list[FileMetric],
) -> None:
    write_json_report(path, metadata=metadata, summary=summary, metrics=metrics)


def write_baseline(
    path: Path,
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: list[FileMetric],
) -> None:
    write_json_report(path, metadata=metadata, summary=summary, metrics=metrics)


def write_csv(path: Path, metrics: list[FileMetric]) -> None:
    write_csv_report(path, metrics, fieldnames=list(FileMetric.__dataclass_fields__))


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
    enterprise = summary.get("enterprise") or {}
    if enterprise:
        print(
            "Enterprise readiness: "
            f"method_body_files={enterprise['files_with_method_bodies']}"
            f"/{summary['files_scanned']} "
            f"({enterprise['method_body_file_rate']:.1%}), "
            f"annotation_stubs={enterprise['annotation_only_stub_files']} "
            f"({enterprise['annotation_only_stub_rate']:.1%}), "
            f"annotation_warnings={enterprise['files_with_annotation_warnings']} files "
            f"({enterprise['total_annotation_warnings']} total)"
        )
    print(f"JSON report: {json_out}")
    print(f"CSV report: {csv_out}")


def _annotation_family_counts_for_sample(
    repo: Path,
    files: list[Path],
    *,
    require_annotations: tuple[str, ...],
) -> dict[str, int]:
    if not require_annotations:
        return {}
    file_texts: list[tuple[str, str]] = []
    for path in files:
        try:
            if path.is_relative_to(repo):
                relative = path.relative_to(repo).as_posix()
            elif path.is_relative_to(REPO_ROOT):
                relative = path.relative_to(REPO_ROOT).as_posix()
            else:
                relative = path.as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            continue
        file_texts.append((relative, text))
    return annotation_family_file_counts(
        file_texts,
        require_annotations=require_annotations,
    )


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
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return proc.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
