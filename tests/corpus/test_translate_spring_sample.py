"""Tests for the Spring corpus scoreboard helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "corpus" / "translate_spring_sample.py"
    spec = importlib.util.spec_from_file_location("translate_spring_sample", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


corpus = _load_script()


def _metric(
    path: str,
    *,
    coverage: float = 1.0,
    handled_count: int = 1,
    parse_ok: bool = True,
    syntax_ok: bool = True,
    unhandled_count: int = 0,
    unhandled_reasons: str = "",
) -> object:
    return corpus.FileMetric(
        path=path,
        parse_ok=parse_ok,
        parse_error_count=0,
        syntax_ok=syntax_ok,
        coverage=coverage,
        handled_count=handled_count,
        unhandled_count=unhandled_count,
        warning_count=0,
        unhandled_node_types="",
        unhandled_reasons=unhandled_reasons,
    )


def test_summarize_tracks_coverage_threshold() -> None:
    summary = corpus.summarize(
        [
            _metric("A.java", coverage=1.0),
            _metric("B.java", coverage=0.75, unhandled_count=1),
            _metric("package-info.java", coverage=0.0, handled_count=0),
        ],
    )

    assert summary["files_scanned"] == 3
    assert summary["coverage_file_count"] == 2
    assert summary["average_coverage"] == 0.875
    assert summary["coverage_threshold"] == 0.8
    assert summary["files_below_coverage_threshold"] == 1
    assert summary["files_with_unhandled"] == 1


def test_compare_baseline_reports_per_file_regressions(tmp_path: Path) -> None:
    baseline_metrics = [
        _metric("A.java", coverage=1.0),
        _metric("B.java", coverage=0.9, unhandled_count=1, unhandled_reasons="old reason:1"),
    ]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 2,
            "include_tests": False,
        },
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    current_metrics = [
        _metric("A.java", coverage=1.0, syntax_ok=False),
        _metric(
            "B.java",
            coverage=0.8,
            unhandled_count=2,
            unhandled_reasons="new reason:1;old reason:1",
        ),
    ]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 2,
            "include_tests": False,
        },
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert "average_coverage" in comparison["regressions"]
    assert comparison["file_regressions"]["syntax_failures"] == [
        {"path": "A.java", "error": ""},
    ]
    assert comparison["file_regressions"]["coverage_drops"][0]["path"] == "B.java"
    assert comparison["file_regressions"]["unhandled_increases"][0]["path"] == "B.java"
    assert comparison["file_regressions"]["new_unhandled_reasons"] == [
        {
            "path": "B.java",
            "reason": "new reason",
            "baseline": 0,
            "current": 1,
            "delta": 1,
        },
    ]

    payload = json.loads(baseline_path.read_text())
    assert payload["files"][0]["path"] == "A.java"
