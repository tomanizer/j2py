#!/usr/bin/env python3
"""Aggregate unhandled-construct hotspots across committed corpus baselines.

Reads ``tests/fixtures/corpus/*-baseline.json`` (or a custom directory), clusters
per-file ``unhandled_reasons``, ranks cross-corpus gaps, and prints a triage report.

Track A (output quality): files with ``syntax_ok=false`` or ``parse_ok=false`` become
ranked clusters even when ``unhandled_reasons`` is empty — coverage alone can mislead.

Priority score: ``hits × corpora × severity``, where severity is 4 (parse failure),
3 (syntax failure), 2 (structural gap), or 1 (expression/import noise). Severity
file counts are deduplicated per cluster/file, not per unhandled reason.

Example::

    uv run python scripts/corpus/aggregate_hotspots.py
    uv run python scripts/corpus/aggregate_hotspots.py --top 12 --json-out corpus-reports/hotspots.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE_DIR = REPO_ROOT / "tests" / "fixtures" / "corpus"

SYNTAX_OUTPUT_CLUSTER = "invalid python output"
PARSE_FAILURE_CLUSTER = "parse failure"

CLUSTER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("unknown static import", re.compile(r"^unknown static import ")),
    ("overloaded method dispatch", re.compile(r"^overloaded method .+ requires manual dispatch$")),
    ("ambiguous get invocation", re.compile(r"^ambiguous get invocation requires receiver collection type$")),
    ("equals unexpected args", re.compile(r"^equals invocation with unexpected argument count$")),
    ("anonymous class scope", re.compile(r"^anonymous class requires local helper scope$")),
    ("enum constant class body", re.compile(r"^enum constant class body requires manual translation$")),
    ("unsupported assert", re.compile(r"^unsupported statement assert_statement$")),
    ("unsupported statement", re.compile(r"^unsupported statement ")),
)

ISSUE_TITLES: dict[str, str] = {
    SYNTAX_OUTPUT_CLUSTER: "P0: Fix invalid Python output (comment-only blocks, wildcard types, …)",
    PARSE_FAILURE_CLUSTER: "Investigate corpus parse failures",
    "unknown static import": "Rule layer: resolve common static imports (Preconditions, Objects.requireNonNull, …)",
    "overloaded method dispatch": "Rule layer: broaden deterministic overload dispatch (ADR 0009 tier-1 patterns)",
    "ambiguous get invocation": "Expressions: disambiguate `.get()` by receiver collection type",
    "enum constant class body": "Classes: translate enum constant class bodies",
    "unsupported assert": "Statements: translate Java assert statements",
    "equals unexpected args": "Expressions: handle equals() invocations with non-standard arity",
    "anonymous class scope": "Classes: anonymous inner classes in local helper scope",
    "unsupported statement": "Statements: extend unsupported statement coverage",
}


def cluster_reason(reason: str) -> str:
    for label, pattern in CLUSTER_PATTERNS:
        if pattern.search(reason):
            return label
    return reason


def parse_counter_summary(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not text:
        return counts
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, _, count_text = part.rpartition(":")
            counts[key.strip()] += int(count_text.strip())
        else:
            counts[part] += 1
    return counts


@dataclass
class Exemplar:
    preset: str
    path: str
    coverage: float
    unhandled_count: int
    syntax_ok: bool
    parse_ok: bool
    construct_size: int


@dataclass
class ClusterStats:
    cluster: str
    total_count: int = 0
    corpora: set[str] = field(default_factory=set)
    file_hits: int = 0
    raw_reasons: Counter[str] = field(default_factory=Counter)
    exemplars: list[Exemplar] = field(default_factory=list)
    syntax_fail_files: int = 0
    parse_fail_files: int = 0

    @property
    def severity(self) -> int:
        if self.parse_fail_files:
            return 4
        if self.syntax_fail_files:
            return 3
        if self.cluster in {
            "overloaded method dispatch",
            "enum constant class body",
            "unsupported assert",
            "unsupported statement",
            "anonymous class scope",
        }:
            return 2
        return 1

    @property
    def priority_score(self) -> float:
        return self.total_count * len(self.corpora) * self.severity


@dataclass
class HotspotReport:
    corpus_summaries: list[dict[str, Any]]
    syntax_failures: list[dict[str, Any]]
    parse_failures: list[dict[str, Any]]
    clusters: list[ClusterStats]


def syntax_failure_bucket(*, unhandled_count: int) -> str:
    if unhandled_count == 0:
        return "syntax failure with no unhandled constructs"
    return "syntax failure with unhandled constructs"


def _file_exemplar(preset: str, file_metric: dict[str, Any]) -> Exemplar:
    return Exemplar(
        preset=preset,
        path=file_metric["path"],
        coverage=float(file_metric.get("coverage", 0)),
        unhandled_count=int(file_metric.get("unhandled_count", 0)),
        syntax_ok=bool(file_metric.get("syntax_ok")),
        parse_ok=bool(file_metric.get("parse_ok")),
        construct_size=int(file_metric.get("handled_count", 0))
        + int(file_metric.get("unhandled_count", 0)),
    )


def _dedupe_exemplars(exemplars: list[Exemplar], *, limit: int = 3) -> list[Exemplar]:
    exemplars.sort(
        key=lambda item: (item.construct_size, item.unhandled_count, -item.coverage, item.path),
    )
    seen_paths: set[str] = set()
    unique: list[Exemplar] = []
    for exemplar in exemplars:
        key = f"{exemplar.preset}:{exemplar.path}"
        if key in seen_paths:
            continue
        seen_paths.add(key)
        unique.append(exemplar)
        if len(unique) >= limit:
            break
    return unique


def _add_output_quality_clusters(
    clusters: dict[str, ClusterStats],
    *,
    preset: str,
    file_metric: dict[str, Any],
) -> None:
    if not file_metric.get("parse_ok"):
        stats = clusters.setdefault(PARSE_FAILURE_CLUSTER, ClusterStats(cluster=PARSE_FAILURE_CLUSTER))
        stats.total_count += 1
        stats.corpora.add(preset)
        stats.file_hits += 1
        stats.parse_fail_files += 1
        stats.raw_reasons["parse_ok=false"] += 1
        stats.exemplars.append(_file_exemplar(preset, file_metric))
        return

    if file_metric.get("syntax_ok"):
        return

    stats = clusters.setdefault(SYNTAX_OUTPUT_CLUSTER, ClusterStats(cluster=SYNTAX_OUTPUT_CLUSTER))
    unhandled_count = int(file_metric.get("unhandled_count", 0))
    stats.total_count += 1
    stats.corpora.add(preset)
    stats.file_hits += 1
    stats.syntax_fail_files += 1
    stats.raw_reasons[syntax_failure_bucket(unhandled_count=unhandled_count)] += 1
    stats.exemplars.append(_file_exemplar(preset, file_metric))


def load_baselines(baseline_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    baselines: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(baseline_dir.glob("*-baseline.json")):
        data = json.loads(path.read_text())
        preset = data.get("metadata", {}).get("preset") or path.stem.replace("-baseline", "")
        baselines.append((preset, data))
    return baselines


def build_report(baseline_dir: Path) -> HotspotReport:
    clusters: dict[str, ClusterStats] = {}
    corpus_summaries: list[dict[str, Any]] = []
    syntax_failures: list[dict[str, Any]] = []
    parse_failures: list[dict[str, Any]] = []

    for preset, data in load_baselines(baseline_dir):
        summary = data["summary"]
        corpus_summaries.append(
            {
                "preset": preset,
                "files_scanned": summary["files_scanned"],
                "average_coverage": summary["average_coverage"],
                "syntax_success_rate": summary["syntax_success_rate"],
                "parse_success_rate": summary["parse_success_rate"],
                "files_with_unhandled": summary["files_with_unhandled"],
                "full_coverage_files": summary["full_coverage_files"],
                "coverage_file_count": summary.get("coverage_file_count", 0),
                "enterprise": summary.get("enterprise") or {},
            },
        )

        for file_metric in data.get("files", []):
            reasons = parse_counter_summary(file_metric.get("unhandled_reasons", ""))
            _add_output_quality_clusters(clusters, preset=preset, file_metric=file_metric)

            if not file_metric.get("parse_ok"):
                parse_failures.append(
                    {
                        "preset": preset,
                        "path": file_metric["path"],
                        "error": file_metric.get("error", ""),
                        "coverage": file_metric.get("coverage", 0),
                    },
                )
            if file_metric.get("parse_ok") and not file_metric.get("syntax_ok"):
                syntax_failures.append(
                    {
                        "preset": preset,
                        "path": file_metric["path"],
                        "error": file_metric.get("error", ""),
                        "coverage": file_metric.get("coverage", 0),
                        "unhandled_count": file_metric.get("unhandled_count", 0),
                        "handled_count": file_metric.get("handled_count", 0),
                        "reasons": dict(reasons),
                    },
                )

            if not reasons:
                continue

            seen_clusters_in_file: set[str] = set()
            exemplar = _file_exemplar(preset, file_metric)
            for reason, count in reasons.items():
                cluster = cluster_reason(reason)
                stats = clusters.setdefault(cluster, ClusterStats(cluster=cluster))
                stats.total_count += count
                stats.corpora.add(preset)
                stats.raw_reasons[reason] += count
                if cluster not in seen_clusters_in_file:
                    stats.file_hits += 1
                    seen_clusters_in_file.add(cluster)
                    if not file_metric.get("syntax_ok"):
                        stats.syntax_fail_files += 1
                    if not file_metric.get("parse_ok"):
                        stats.parse_fail_files += 1
                    stats.exemplars.append(exemplar)

    for stats in clusters.values():
        stats.exemplars = _dedupe_exemplars(stats.exemplars)

    ranked_clusters = sorted(
        clusters.values(),
        key=lambda item: (-item.priority_score, -item.total_count, -len(item.corpora), item.cluster),
    )
    return HotspotReport(
        corpus_summaries=corpus_summaries,
        syntax_failures=syntax_failures,
        parse_failures=parse_failures,
        clusters=ranked_clusters,
    )


def _format_pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def print_report(report: HotspotReport, *, top: int) -> None:
    print("=" * 72)
    print("CORPUS SCORECARD (committed baselines)")
    print("=" * 72)
    for summary in sorted(report.corpus_summaries, key=lambda item: item["preset"]):
        line = (
            f"{summary['preset']:22} cov={_format_pct(summary['average_coverage'])}  "
            f"syntax={_format_pct(summary['syntax_success_rate'])}  "
            f"unhandled_files={summary['files_with_unhandled']:3}/{summary['files_scanned']:<3}  "
            f"full_cov={summary['full_coverage_files']}/{summary['coverage_file_count']}"
        )
        enterprise = summary.get("enterprise") or {}
        if enterprise:
            line += (
                f"  bodies={enterprise.get('method_body_file_rate', 0):.0%}"
                f" stubs={enterprise.get('annotation_only_stub_rate', 0):.0%}"
                f" ann_warn={enterprise.get('total_annotation_warnings', 0)}"
            )
        print(line)

    print("\n" + "=" * 72)
    print("SYNTAX FAILURES (parse ok, generated Python invalid)")
    print("=" * 72)
    syntax_failures = sorted(
        report.syntax_failures,
        key=lambda item: (-item["coverage"], item["preset"], item["path"]),
    )
    if not syntax_failures:
        print("(none)")
    else:
        for item in syntax_failures[:20]:
            print(f"  [{item['preset']}] cov={item['coverage']:.2f}  {item['path']}")

    print("\n" + "=" * 72)
    print("PARSE FAILURES")
    print("=" * 72)
    if not report.parse_failures:
        print("(none)")
    else:
        for item in report.parse_failures[:10]:
            error = item.get("error", "")[:100]
            print(f"  [{item['preset']}] {item['path']}: {error}")

    print("\n" + "=" * 72)
    print("RANKED HOTSPOT BACKLOG (unhandled clusters + output quality)")
    print("=" * 72)
    print(f"{'#':<3} {'score':>7} {'sev':>3} {'cnt':>5} {'corp':>4} {'files':>5}  cluster")
    print("-" * 72)
    for index, stats in enumerate(report.clusters[:top], 1):
        print(
            f"{index:<3} {stats.priority_score:7.0f} {stats.severity:>3} {stats.total_count:>5} "
            f"{len(stats.corpora):>4} {stats.file_hits:>5}  {stats.cluster}",
        )

    detail_count = min(top, 12)
    print("\n" + "=" * 72)
    print(f"TOP {detail_count} CLUSTERS — DETAIL")
    print("=" * 72)
    for index, stats in enumerate(report.clusters[:detail_count], 1):
        print(f"\n## {index}. {stats.cluster}")
        print(
            f"   priority={stats.priority_score:.0f}  count={stats.total_count}  "
            f"corpora={len(stats.corpora)}  files={stats.file_hits}  severity={stats.severity}",
        )
        print(f"   corpora: {', '.join(sorted(stats.corpora))}")
        for reason, count in stats.raw_reasons.most_common(5):
            print(f"     - {count:3}x  {reason}")
        print("   exemplars:")
        for exemplar in stats.exemplars:
            status = "syntax_ok" if exemplar.syntax_ok else "SYNTAX_FAIL"
            print(
                f"     - [{exemplar.preset}] {exemplar.path}  cov={exemplar.coverage:.2f}  "
                f"unhandled={exemplar.unhandled_count}  size={exemplar.construct_size}  {status}",
            )

    static = next((item for item in report.clusters if item.cluster == "unknown static import"), None)
    if static is not None:
        print("\n" + "=" * 72)
        print("STATIC IMPORT SUB-BREAKDOWN")
        print("=" * 72)
        symbol_counts: Counter[str] = Counter()
        for reason, count in static.raw_reasons.items():
            match = re.match(r"unknown static import (.+)$", reason)
            if match:
                symbol = match.group(1).rsplit(".", 1)[-1]
                symbol_counts[symbol] += count
        for symbol, count in symbol_counts.most_common(15):
            print(f"  {count:3}x  {symbol}")

    print("\n" + "=" * 72)
    print(f"SUGGESTED ISSUE BACKLOG (top {min(8, top)})")
    print("=" * 72)
    for index, stats in enumerate(report.clusters[: min(8, top)], 1):
        title = ISSUE_TITLES.get(stats.cluster, stats.cluster)
        print(f"\n{index}. {title}")
        print(
            f"   Score {stats.priority_score:.0f} | {stats.total_count} hits across "
            f"{len(stats.corpora)} corpora ({', '.join(sorted(stats.corpora))})",
        )
        if stats.exemplars:
            exemplar = stats.exemplars[0]
            print(f"   Start with: [{exemplar.preset}] {exemplar.path}")


def report_to_json(report: HotspotReport) -> dict[str, Any]:
    return {
        "corpus_summaries": report.corpus_summaries,
        "syntax_failures": report.syntax_failures,
        "parse_failures": report.parse_failures,
        "clusters": [
            {
                **asdict(stats),
                "corpora": sorted(stats.corpora),
                "raw_reasons": stats.raw_reasons.most_common(),
                "priority_score": stats.priority_score,
                "severity": stats.severity,
            }
            for stats in report.clusters
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=DEFAULT_BASELINE_DIR,
        help=f"Directory containing *-baseline.json files (default: {DEFAULT_BASELINE_DIR})",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Number of ranked clusters to show in the summary table (default: 25)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write structured JSON report",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.baseline_dir.is_dir():
        print(f"Baseline directory not found: {args.baseline_dir}", file=sys.stderr)
        return 1

    report = build_report(args.baseline_dir)
    if not report.corpus_summaries:
        print(f"No *-baseline.json files found in {args.baseline_dir}", file=sys.stderr)
        return 1

    print_report(report, top=args.top)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report_to_json(report), indent=2) + "\n")
        print(f"\nWrote JSON report to {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
