"""Tests for cross-corpus hotspot aggregation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_hotspots() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "corpus" / "aggregate_hotspots.py"
    spec = importlib.util.spec_from_file_location("aggregate_hotspots", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hotspots = _load_hotspots()


def _baseline(
    preset: str,
    files: list[dict[str, object]],
    *,
    files_scanned: int | None = None,
) -> dict[str, object]:
    scanned = files_scanned if files_scanned is not None else len(files)
    return {
        "metadata": {"preset": preset},
        "summary": {
            "files_scanned": scanned,
            "average_coverage": 1.0,
            "syntax_success_rate": 1.0,
            "parse_success_rate": 1.0,
            "files_with_unhandled": sum(int(f.get("unhandled_count", 0)) > 0 for f in files),
            "full_coverage_files": len(files),
            "coverage_file_count": len(files),
        },
        "files": files,
    }


def _write_baseline(tmp_path: Path, name: str, payload: dict[str, object]) -> None:
    (tmp_path / f"{name}-baseline.json").write_text(json.dumps(payload))


def test_severity_not_double_counted_for_multiple_reasons(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path,
        "demo",
        _baseline(
            "demo-dense",
            [
                {
                    "path": "Example.java",
                    "parse_ok": True,
                    "syntax_ok": False,
                    "coverage": 1.0,
                    "handled_count": 10,
                    "unhandled_count": 3,
                    "unhandled_reasons": (
                        "ambiguous get invocation requires receiver collection type:2;"
                        "overloaded method of requires manual dispatch:1"
                    ),
                },
            ],
        ),
    )

    report = hotspots.build_report(tmp_path)
    ambiguous = next(item for item in report.clusters if item.cluster == "ambiguous get invocation")

    assert ambiguous.file_hits == 1
    assert ambiguous.syntax_fail_files == 1
    assert ambiguous.total_count == 2


def test_overload_manual_dispatch_with_shape_details_still_clusters(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path,
        "demo",
        _baseline(
            "demo-dense",
            [
                {
                    "path": "GenericCollision.java",
                    "parse_ok": True,
                    "syntax_ok": True,
                    "coverage": 0.5,
                    "handled_count": 1,
                    "unhandled_count": 2,
                    "unhandled_reasons": (
                        "overloaded method first requires manual dispatch "
                        "[erased=(list)|(list) | "
                        "java_shapes=(collection:List->list[string:String->str])|"
                        "(collection:List->list[numeric:Integer->int])]:2"
                    ),
                },
            ],
        ),
    )

    report = hotspots.build_report(tmp_path)
    overload = next(
        item for item in report.clusters if item.cluster == "overloaded method dispatch"
    )

    assert overload.total_count == 2
    assert overload.file_hits == 1


def test_syntax_failure_without_unhandled_appears_in_ranked_clusters(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path,
        "demo",
        _baseline(
            "demo-dense",
            [
                {
                    "path": "src/function/Consumers.java",
                    "parse_ok": True,
                    "syntax_ok": False,
                    "coverage": 1.0,
                    "handled_count": 5,
                    "unhandled_count": 0,
                    "unhandled_reasons": "",
                },
            ],
        ),
    )

    report = hotspots.build_report(tmp_path)
    syntax_cluster = next(
        item for item in report.clusters if item.cluster == hotspots.SYNTAX_OUTPUT_CLUSTER
    )

    assert syntax_cluster.file_hits == 1
    assert syntax_cluster.total_count == 1
    assert syntax_cluster.severity == 3
    assert syntax_cluster.raw_reasons["syntax failure with no unhandled constructs"] == 1
    assert syntax_cluster.exemplars[0].path == "src/function/Consumers.java"


def test_syntax_failure_track_outranks_low_volume_unhandled_clusters(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path,
        "alpha",
        _baseline(
            "alpha-dense",
            [
                {
                    "path": "A.java",
                    "parse_ok": True,
                    "syntax_ok": False,
                    "coverage": 1.0,
                    "handled_count": 4,
                    "unhandled_count": 0,
                    "unhandled_reasons": "",
                },
                {
                    "path": "B.java",
                    "parse_ok": True,
                    "syntax_ok": False,
                    "coverage": 1.0,
                    "handled_count": 6,
                    "unhandled_count": 0,
                    "unhandled_reasons": "",
                },
            ],
        ),
    )
    _write_baseline(
        tmp_path,
        "beta",
        _baseline(
            "beta-dense",
            [
                {
                    "path": "C.java",
                    "parse_ok": True,
                    "syntax_ok": True,
                    "coverage": 0.9,
                    "handled_count": 8,
                    "unhandled_count": 1,
                    "unhandled_reasons": "anonymous class requires local helper scope:1",
                },
            ],
        ),
    )

    report = hotspots.build_report(tmp_path)
    top = report.clusters[0]

    assert top.cluster == hotspots.SYNTAX_OUTPUT_CLUSTER
    assert top.file_hits == 2
    assert top.priority_score == 2 * 1 * 3


def test_parse_failure_cluster_is_separate_track(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path,
        "demo",
        _baseline(
            "demo-dense",
            [
                {
                    "path": "Platform.java",
                    "parse_ok": False,
                    "syntax_ok": False,
                    "coverage": 0.0,
                    "handled_count": 0,
                    "unhandled_count": 0,
                    "unhandled_reasons": "",
                },
            ],
        ),
    )

    report = hotspots.build_report(tmp_path)
    parse_cluster = next(
        item for item in report.clusters if item.cluster == hotspots.PARSE_FAILURE_CLUSTER
    )

    assert parse_cluster.file_hits == 1
    assert parse_cluster.severity == 4
    assert hotspots.SYNTAX_OUTPUT_CLUSTER not in {item.cluster for item in report.clusters}


def test_structured_binding_diagnostics_cluster_by_category(tmp_path: Path) -> None:
    _write_baseline(
        tmp_path,
        "demo",
        _baseline(
            "demo-dense",
            [
                {
                    "path": "AmbiguousGet.java",
                    "parse_ok": True,
                    "syntax_ok": True,
                    "coverage": 0.9,
                    "handled_count": 8,
                    "unhandled_count": 1,
                    "unhandled_reasons": (
                        "ambiguous get invocation requires receiver collection type:1"
                    ),
                    "binding_diagnostics": [
                        {
                            "category": "missing_receiver_type",
                            "reason": "ambiguous get invocation requires receiver collection type",
                            "facts": {"receiver": "values"},
                        },
                    ],
                },
            ],
        ),
    )

    report = hotspots.build_report(tmp_path)
    structured = next(item for item in report.clusters if item.cluster == "missing_receiver_type")

    assert structured.total_count == 1
    assert structured.file_hits == 1
    assert structured.raw_reasons["ambiguous get invocation requires receiver collection type"] == 1
