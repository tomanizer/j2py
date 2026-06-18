"""Baseline comparison helpers for corpus scoreboards."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from counter_summary import parse_counter_summary

_OVERLOAD_MANUAL_DISPATCH_RE = re.compile(
    r"^(overloaded method .+ requires manual dispatch)(?: \[.*\])?$",
)


def compare_baseline(
    path: Path,
    *,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    metrics: Iterable[Any],
) -> dict[str, Any]:
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline_summary = baseline["summary"]
    baseline_metadata = baseline.get("metadata", {})

    metadata_mismatches = _metadata_mismatches(baseline_metadata, metadata)

    deltas: dict[str, dict[str, Any]] = {}
    enterprise_deltas: dict[str, dict[str, Any]] = {}
    regressions: list[str] = []
    improvements: list[str] = []

    if not metadata_mismatches:
        # Only compute deltas when samples are comparable.
        metric_specs = {
            "parse_success_rate": "higher",
            "syntax_success_rate": "higher",
            "average_coverage": "higher",
            "full_coverage_files": "higher",
            "files_with_unhandled": "lower",
            "files_below_coverage_threshold": "lower",
        }
        enterprise_specs = {
            "method_body_file_rate": "higher",
            "annotation_only_stub_rate": "lower",
            "annotation_warning_file_rate": "lower",
            "total_annotation_warnings": "lower",
        }
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

        baseline_enterprise = baseline_summary.get("enterprise") or {}
        current_enterprise = summary.get("enterprise") or {}
        if baseline_enterprise and current_enterprise:
            for metric, direction in enterprise_specs.items():
                baseline_value = baseline_enterprise.get(metric)
                current_value = current_enterprise.get(metric)
                if baseline_value is None or current_value is None:
                    continue
                delta = current_value - baseline_value
                enterprise_deltas[metric] = {
                    "baseline": baseline_value,
                    "current": current_value,
                    "delta": delta,
                    "direction": direction,
                }

    file_regressions = (
        _empty_file_regressions()
        if metadata_mismatches
        else _file_regressions(
            baseline.get("files", []),
            [asdict(metric) for metric in metrics],
        )
    )

    return {
        "baseline_path": str(path),
        "deltas": deltas,
        "enterprise_deltas": enterprise_deltas,
        "improvements": improvements,
        "regressions": regressions,
        "metadata_mismatches": metadata_mismatches,
        "file_regressions": file_regressions,
        "baseline_top_unhandled_node_types": baseline_summary["top_unhandled_node_types"],
        "current_top_unhandled_node_types": summary["top_unhandled_node_types"],
        "baseline_top_unhandled_reasons": baseline_summary["top_unhandled_reasons"],
        "current_top_unhandled_reasons": summary["top_unhandled_reasons"],
    }


def print_comparison(comparison: dict[str, Any]) -> None:
    print(f"Baseline comparison: {comparison['baseline_path']}")
    if comparison["metadata_mismatches"]:
        print(f"  Metadata mismatch: {', '.join(comparison['metadata_mismatches'])}")
        print(
            "  WARNING: Samples are not directly comparable "
            "(different strategy, modules, limits, or construct inclusion).",
        )
        print("  Deltas and improvement/regression counts below are suppressed.")
    else:
        for metric, values in comparison["deltas"].items():
            print(
                f"  {metric}: {_format_metric(values['baseline'])} -> "
                f"{_format_metric(values['current'])} ({_format_delta(values['delta'])})"
            )
    if not comparison["metadata_mismatches"]:
        if comparison["improvements"]:
            print(f"Improvements: {', '.join(comparison['improvements'])}")
        if comparison["regressions"]:
            print(f"Regressions: {', '.join(comparison['regressions'])}")
        else:
            print("Regressions: none")
        enterprise_deltas = comparison.get("enterprise_deltas") or {}
        if enterprise_deltas:
            print("Enterprise readiness deltas:")
            for metric, values in enterprise_deltas.items():
                print(
                    f"  {metric}: {_format_metric(values['baseline'])} -> "
                    f"{_format_metric(values['current'])} ({_format_delta(values['delta'])})"
                )
    print("Top unhandled node types:")
    print(f"  baseline: {_top_list(comparison['baseline_top_unhandled_node_types'])}")
    print(f"  current:  {_top_list(comparison['current_top_unhandled_node_types'])}")
    _print_file_regressions(comparison["file_regressions"])


def has_file_regressions(file_regressions: dict[str, list[dict[str, Any]]]) -> bool:
    return any(file_regressions.values())


def _metadata_comparable_keys(
    baseline_metadata: dict[str, Any],
    metadata: dict[str, Any],
) -> list[str]:
    ref_key = "corpus_ref" if "corpus_ref" in baseline_metadata else "spring_ref"
    keys = [
        ref_key,
        "modules",
        "limit",
        "include_tests",
        "strategy",
        "max_loc",
        "min_loc",
        "min_constructs",
        "include_constructs",
        "skip_package_info",
        "exclude_paths",
        "include_path_prefixes",
        "require_annotations",
        "min_annotation_hits",
    ]
    if baseline_metadata.get("preset") and metadata.get("preset"):
        return ["preset", *keys]
    return keys


def _metadata_mismatches(
    baseline_metadata: dict[str, Any],
    metadata: dict[str, Any],
) -> list[str]:
    return [
        key
        for key in _metadata_comparable_keys(baseline_metadata, metadata)
        if not _metadata_values_match(key, baseline_metadata, metadata)
    ]


def _metadata_values_match(
    key: str,
    baseline_metadata: dict[str, Any],
    metadata: dict[str, Any],
) -> bool:
    if key == "exclude_paths":
        return set(baseline_metadata.get(key) or []) == set(metadata.get(key) or [])
    if key == "require_annotations":
        return set(baseline_metadata.get(key) or []) == set(metadata.get(key) or [])
    if key in {"skip_package_info", "include_path_prefixes"}:
        if key == "include_path_prefixes":
            return set(baseline_metadata.get(key) or []) == set(metadata.get(key) or [])
        return bool(baseline_metadata.get(key, False)) == bool(metadata.get(key, False))
    if key == "min_loc":
        return int(baseline_metadata.get(key) or 0) == int(metadata.get(key) or 0)
    if key == "min_annotation_hits":
        return int(baseline_metadata.get(key) or 0) == int(metadata.get(key) or 0)
    return baseline_metadata.get(key) == metadata.get(key)


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

        baseline_reasons = _canonical_unhandled_reasons(
            parse_counter_summary(baseline.get("unhandled_reasons", "")),
        )
        current_reasons = _canonical_unhandled_reasons(
            parse_counter_summary(current.get("unhandled_reasons", "")),
        )
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


def _canonical_unhandled_reasons(reasons: dict[str, int]) -> dict[str, int]:
    canonical: dict[str, int] = {}
    for reason, count in reasons.items():
        key = _canonical_unhandled_reason(reason)
        canonical[key] = canonical.get(key, 0) + count
    return canonical


def _canonical_unhandled_reason(reason: str) -> str:
    overload = _OVERLOAD_MANUAL_DISPATCH_RE.match(reason)
    if overload:
        return overload.group(1)
    return reason


def _empty_file_regressions() -> dict[str, list[dict[str, Any]]]:
    return {
        "parse_failures": [],
        "syntax_failures": [],
        "coverage_drops": [],
        "unhandled_increases": [],
        "new_unhandled_reasons": [],
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
