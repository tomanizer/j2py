from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def coverage_floor_module():
    path = Path(__file__).resolve().parents[2] / "scripts/packaging/check_coverage_floor.py"
    spec = importlib.util.spec_from_file_location("check_coverage_floor", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_coverage_floor_accepts_line_rate_at_threshold(
    tmp_path: Path,
    coverage_floor_module,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text('<coverage line-rate="0.90" branch-rate="0.50" />', encoding="utf-8")

    assert coverage_floor_module.check_coverage_floor(coverage_xml, 90.0) is None


def test_coverage_floor_reports_line_rate_below_threshold(
    tmp_path: Path,
    coverage_floor_module,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text('<coverage line-rate="0.899" branch-rate="0.95" />', encoding="utf-8")

    error = coverage_floor_module.check_coverage_floor(coverage_xml, 90.0)

    assert error is not None
    assert "89.90%" in error
    assert "90.00%" in error
