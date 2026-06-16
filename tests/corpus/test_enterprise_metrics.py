"""Tests for enterprise readiness corpus metrics."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from j2py.parse.java_ast import parse_source


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_SCRIPT_DIR = Path(__file__).parents[2] / "scripts" / "corpus"
enterprise = _load_module("enterprise_metrics", _SCRIPT_DIR / "enterprise_metrics.py")


def test_count_method_bodies_ignores_empty_blocks() -> None:
    source = """
    public class Demo {
        public void empty() {}
        public void withBody() { return; }
        public Demo() {}
    }
    """
    parsed = parse_source(source, path=Path("Demo.java"))
    assert enterprise.count_method_bodies(parsed) == 1


def test_count_annotation_warnings_matches_reason_substrings() -> None:
    warnings = (
        type("W", (), {"reason": "unsupported annotation RestController"})(),
        type("W", (), {"reason": "unhandled node"})(),
        type("W", (), {"reason": "preserved annotation Entity"})(),
    )
    assert enterprise.count_annotation_warnings(warnings) == 2


def test_file_enterprise_signals_detects_annotation_only_stub() -> None:
    source = """
    @Configuration
    public class ConfigOnly {
    }
    """
    parsed = parse_source(source, path=Path("ConfigOnly.java"))
    signals = enterprise.file_enterprise_signals(
        parsed=parsed,
        source_text=source,
        warnings=(),
        annotation_names=("Configuration",),
    )
    assert signals.method_body_count == 0
    assert signals.annotation_use_count == 1
    assert signals.is_annotation_only_stub is True


def test_summarize_enterprise_aggregates_rates() -> None:
    class Metric:
        method_body_count: int
        annotation_use_count: int
        annotation_warning_count: int

        def __init__(
            self,
            *,
            method_body_count: int,
            annotation_use_count: int,
            annotation_warning_count: int,
        ) -> None:
            self.method_body_count = method_body_count
            self.annotation_use_count = annotation_use_count
            self.annotation_warning_count = annotation_warning_count

    summary = enterprise.summarize_enterprise(
        [
            Metric(method_body_count=2, annotation_use_count=3, annotation_warning_count=1),
            Metric(method_body_count=0, annotation_use_count=1, annotation_warning_count=0),
        ],
    )
    assert summary["files_with_method_bodies"] == 1
    assert summary["method_body_file_rate"] == 0.5
    assert summary["annotation_only_stub_files"] == 1
    assert summary["annotation_only_stub_rate"] == 0.5
    assert summary["total_annotation_warnings"] == 1
