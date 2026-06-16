"""Tests for the multi-library corpus scoreboard helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "corpus" / "translate_corpus.py"
    spec = importlib.util.spec_from_file_location("translate_corpus", path)
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


def test_summarize_includes_enterprise_block() -> None:
    summary = corpus.summarize(
        [
            corpus.FileMetric(
                path="Config.java",
                parse_ok=True,
                parse_error_count=0,
                syntax_ok=True,
                coverage=1.0,
                handled_count=5,
                unhandled_count=0,
                warning_count=0,
                method_body_count=0,
                annotation_use_count=2,
                annotation_warning_count=0,
                unhandled_node_types="",
                unhandled_reasons="",
            ),
            corpus.FileMetric(
                path="Service.java",
                parse_ok=True,
                parse_error_count=0,
                syntax_ok=True,
                coverage=1.0,
                handled_count=10,
                unhandled_count=0,
                warning_count=1,
                method_body_count=3,
                annotation_use_count=1,
                annotation_warning_count=1,
                unhandled_node_types="",
                unhandled_reasons="",
            ),
        ],
    )

    enterprise = summary["enterprise"]
    assert enterprise["files_with_method_bodies"] == 1
    assert enterprise["method_body_file_rate"] == 0.5
    assert enterprise["annotation_only_stub_files"] == 1
    assert enterprise["total_annotation_warnings"] == 1


def test_counter_summary_escapes_semicolons_in_diagnostic_reasons() -> None:
    summary = corpus._counter_summary(
        {
            "unsupported expression; fallback emitted": 2,
            "method_invocation": 1,
        },
    )

    assert corpus._parse_counter_summary(summary) == {
        "unsupported expression; fallback emitted": 2,
        "method_invocation": 1,
    }


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


def test_compare_baseline_missing_file_exits_with_clear_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    source_dir = repo / "src" / "main" / "java"
    source_dir.mkdir(parents=True)
    (source_dir / "A.java").write_text(
        "public class A { private int count; }\n",
        encoding="utf-8",
    )
    missing_baseline = tmp_path / "missing-baseline.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "translate_corpus.py",
            "--repo",
            str(repo),
            "--remote",
            "local",
            "--ref",
            "local",
            "--module",
            "src/main/java",
            "--limit",
            "1",
            "--json-out",
            str(tmp_path / "out.json"),
            "--csv-out",
            str(tmp_path / "out.csv"),
            "--baseline",
            str(missing_baseline),
            "--compare-baseline",
        ],
    )

    assert corpus.main() == 2
    captured = capsys.readouterr()
    assert f"Baseline file not found: {missing_baseline}" in captured.err
    assert "Traceback" not in captured.err


def test_measure_file_falls_back_for_paths_outside_spring_repo() -> None:
    """Ensure curated construct files (outside the Spring checkout) do not crash measure_file.

    This covers the P1 fix: paths from tests/fixtures/corpus/constructs are reported
    with a project-relative path instead of raising ValueError on .relative_to().
    """
    # Use a real construct file that exists in the source tree
    construct = corpus.CONSTRUCTS_DIR / "VarKeyword.java"
    assert construct.exists(), "Expected curated construct file for test"

    fake_spring_repo = Path("/tmp/fake-spring-repo")  # guaranteed not to contain the construct

    cfg = corpus.ConfigLoader().add_defaults().build()
    metric = corpus.measure_file(construct, repo=fake_spring_repo, cfg=cfg)

    # Should succeed and produce a sensible relative path under the j2py project
    assert "constructs/VarKeyword.java" in metric.path
    assert not metric.path.startswith("/tmp")
    assert metric.parse_ok is True
    assert metric.handled_count + metric.unhandled_count > 0


def test_collect_java_files_prioritizes_curated_constructs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    module = repo / "module" / "src" / "main" / "java" / "example"
    module.mkdir(parents=True)
    for index in range(5):
        (module / f"A{index}.java").write_text(
            f"package example;\nclass A{index} {{ void run() {{ }} }}\n",
        )

    constructs_dir = tmp_path / "zz_constructs"
    constructs_dir.mkdir()
    construct_one = constructs_dir / "ConstructOne.java"
    construct_two = constructs_dir / "ConstructTwo.java"
    construct_one.write_text("package example;\nclass ConstructOne { void run() { } }\n")
    construct_two.write_text("package example;\nclass ConstructTwo { void run() { } }\n")
    monkeypatch.setattr(corpus, "CONSTRUCTS_DIR", constructs_dir)

    selected = corpus.collect_java_files(
        repo,
        modules=("module/src/main/java",),
        limit=3,
        include_tests=False,
        strategy="lexical",
        include_constructs=True,
    )

    assert construct_one in selected
    assert construct_two in selected
    assert len(selected) == 3


def test_collect_java_files_skips_package_info_by_default(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = repo / "module" / "src" / "main" / "java" / "example"
    module.mkdir(parents=True)
    real = module / "Real.java"
    package_info = module / "package-info.java"
    real.write_text("package example;\nclass Real { }\n")
    package_info.write_text("@Deprecated\npackage example;\n")

    selected = corpus.collect_java_files(
        repo,
        modules=("module/src/main/java",),
        limit=10,
        include_tests=False,
        strategy="lexical",
    )

    assert real in selected
    assert package_info not in selected


def test_collect_java_files_can_include_package_info(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = repo / "module" / "src" / "main" / "java" / "example"
    module.mkdir(parents=True)
    real = module / "Real.java"
    package_info = module / "package-info.java"
    real.write_text("package example;\nclass Real { }\n")
    package_info.write_text("@Deprecated\npackage example;\n")

    selected = corpus.collect_java_files(
        repo,
        modules=("module/src/main/java",),
        limit=10,
        include_tests=False,
        strategy="lexical",
        skip_package_info=False,
    )

    assert real in selected
    assert package_info in selected


def test_collect_java_files_respects_min_loc(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = repo / "module" / "src" / "main" / "java" / "example"
    module.mkdir(parents=True)
    tiny = module / "Tiny.java"
    substantial = module / "Substantial.java"
    tiny.write_text("package example;\nclass Tiny { }\n")
    substantial.write_text(
        "package example;\n"
        + "".join(f"    void m{i}() {{ }}\n" for i in range(25))
        + "class Substantial { }\n",
    )

    selected = corpus.collect_java_files(
        repo,
        modules=("module/src/main/java",),
        limit=10,
        include_tests=False,
        strategy="lexical",
        min_loc=20,
    )

    assert substantial in selected
    assert tiny not in selected


def test_collect_java_files_pins_path_prefixes_before_density(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    pinned_dir = repo / "module" / "src" / "main" / "java" / "di"
    other_dir = repo / "module" / "src" / "main" / "java" / "other"
    pinned_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    pinned = pinned_dir / "Autowired.java"
    other = other_dir / "Other.java"
    pinned.write_text("package di;\nclass Autowired { }\n")
    other.write_text("package other;\nclass Other { void run() { } }\n")
    monkeypatch.setattr(corpus, "CONSTRUCTS_DIR", tmp_path / "empty_constructs")

    selected = corpus.collect_java_files(
        repo,
        modules=("module/src/main/java",),
        limit=1,
        include_tests=False,
        strategy="density",
        include_path_prefixes=("module/src/main/java/di/",),
    )

    assert pinned in selected
    assert other not in selected


def test_collect_java_files_respects_exclude_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    module = repo / "guava" / "src" / "com" / "google" / "common" / "base"
    module.mkdir(parents=True)
    included = module / "Included.java"
    excluded = module / "Platform.java"
    included.write_text("package com.google.common.base;\nclass Included { }\n")
    excluded.write_text("package com.google.common.base;\nclass Platform { }\n")

    selected = corpus.collect_java_files(
        repo,
        modules=("guava/src/com/google/common/base",),
        limit=10,
        include_tests=False,
        strategy="lexical",
        exclude_paths=("guava/src/com/google/common/base/Platform.java",),
    )

    assert included in selected
    assert excluded not in selected


def test_compare_baseline_suppresses_deltas_on_metadata_mismatch(tmp_path: Path) -> None:
    """Metadata mismatches (different strategy, include_constructs, etc.) must suppress deltas.

    This covers the P2 fix: when baseline and current have different sampling parameters,
    compare_baseline returns empty deltas/improvements/regressions and populates
    metadata_mismatches. The existing test only covered the comparable (matching metadata) case.
    """
    baseline_metrics = [
        _metric("A.java", coverage=1.0),
    ]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "lexical",
            "include_constructs": False,
        },
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    current_metrics = [
        _metric("A.java", coverage=0.5),
    ]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",  # deliberate mismatch
            "include_constructs": True,
        },
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert comparison["metadata_mismatches"]  # should be non-empty
    assert comparison["deltas"] == {}
    assert comparison["improvements"] == []
    assert comparison["regressions"] == []
    assert comparison["file_regressions"] == {
        "parse_failures": [],
        "syntax_failures": [],
        "coverage_drops": [],
        "unhandled_increases": [],
        "new_unhandled_reasons": [],
    }


def test_compare_baseline_treats_missing_exclude_paths_as_empty(tmp_path: Path) -> None:
    baseline_metrics = [_metric("A.java", coverage=1.0)]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
        },
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    current_metrics = [_metric("A.java", coverage=0.5)]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
            "exclude_paths": [],
        },
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert comparison["metadata_mismatches"] == []
    assert comparison["deltas"]
    assert "average_coverage" in comparison["regressions"]


def test_compare_baseline_missing_exclude_paths_still_mismatches_non_empty_current(
    tmp_path: Path,
) -> None:
    baseline_metrics = [_metric("A.java", coverage=1.0)]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
        },
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    current_metrics = [_metric("A.java", coverage=0.5)]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
            "exclude_paths": ["module/Excluded.java"],
        },
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert comparison["metadata_mismatches"] == ["exclude_paths"]
    assert comparison["deltas"] == {}


def test_compare_baseline_exclude_paths_order_insensitive(tmp_path: Path) -> None:
    baseline_metrics = [_metric("A.java", coverage=1.0)]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
            "exclude_paths": ["module/B.java", "module/A.java"],
        },
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    current_metrics = [_metric("A.java", coverage=0.5)]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
            "exclude_paths": ["module/A.java", "module/B.java"],
        },
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert comparison["metadata_mismatches"] == []


def test_compare_baseline_treats_null_exclude_paths_as_empty(tmp_path: Path) -> None:
    baseline_metrics = [_metric("A.java", coverage=1.0)]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
            "exclude_paths": None,
        },
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    current_metrics = [_metric("A.java", coverage=0.5)]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
            "exclude_paths": [],
        },
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert comparison["metadata_mismatches"] == []


def test_compare_baseline_still_mismatches_unrelated_metadata(tmp_path: Path) -> None:
    baseline_metrics = [_metric("A.java", coverage=1.0)]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "lexical",
            "include_constructs": True,
            "exclude_paths": [],
        },
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    current_metrics = [_metric("A.java", coverage=0.5)]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={
            "spring_ref": "ref",
            "modules": ["module"],
            "limit": 1,
            "include_tests": False,
            "strategy": "density",
            "include_constructs": True,
            "exclude_paths": [],
        },
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert comparison["metadata_mismatches"] == ["strategy"]
    assert comparison["deltas"] == {}


def test_has_file_regressions_is_true_on_per_file_syntax_failure(tmp_path: Path) -> None:
    """A single file flipping syntax_ok: true → false must make _has_file_regressions return True,
    even when the global syntax_success_rate does not change (e.g. another file improved)."""
    baseline_metrics = [
        _metric("A.java", syntax_ok=True),
        _metric("B.java", syntax_ok=False),
    ]
    baseline_path = tmp_path / "baseline.json"
    corpus.write_baseline(
        baseline_path,
        metadata={"spring_ref": "ref", "modules": ["m"], "limit": 2, "include_tests": False},
        summary=corpus.summarize(baseline_metrics),
        metrics=baseline_metrics,
    )

    # A regresses; B improves.  Global syntax_success_rate stays 50% → 50%.
    current_metrics = [
        _metric("A.java", syntax_ok=False),
        _metric("B.java", syntax_ok=True),
    ]
    comparison = corpus.compare_baseline(
        baseline_path,
        metadata={"spring_ref": "ref", "modules": ["m"], "limit": 2, "include_tests": False},
        summary=corpus.summarize(current_metrics),
        metrics=current_metrics,
    )

    assert comparison["file_regressions"]["syntax_failures"] == [{"path": "A.java", "error": ""}]
    assert corpus._has_file_regressions(comparison["file_regressions"]) is True
    # The aggregate syntax_success_rate did NOT change, so it's not in regressions.
    assert "syntax_success_rate" not in comparison["regressions"]
