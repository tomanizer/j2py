from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="session")
def coverage_floor_module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts/packaging/check_coverage_floor.py"
    spec = importlib.util.spec_from_file_location("check_coverage_floor", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_coverage_floor_accepts_line_rate_at_threshold(
    tmp_path: Path,
    coverage_floor_module: ModuleType,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text('<coverage line-rate="0.90" branch-rate="0.81" />', encoding="utf-8")

    assert coverage_floor_module.check_coverage_floor(coverage_xml, 90.0, 81.0) == []


def test_coverage_floor_uses_committed_floor_by_default(
    tmp_path: Path,
    coverage_floor_module: ModuleType,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text('<coverage line-rate="0.90" branch-rate="0.81" />', encoding="utf-8")

    assert coverage_floor_module.check_coverage_floor(coverage_xml) == []


def test_coverage_floor_can_load_custom_floor_file(
    tmp_path: Path,
    coverage_floor_module: ModuleType,
) -> None:
    floor = tmp_path / "coverage-floor.json"
    floor.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "line_percent": 91.0,
                "branch_percent": 82.0,
            }
        ),
        encoding="utf-8",
    )

    assert coverage_floor_module.load_coverage_floor(floor) == (91.0, 82.0)


def test_coverage_floor_reports_line_rate_below_threshold(
    tmp_path: Path,
    coverage_floor_module: ModuleType,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text('<coverage line-rate="0.899" branch-rate="0.95" />', encoding="utf-8")

    errors = coverage_floor_module.check_coverage_floor(coverage_xml, 90.0, 81.0)

    assert len(errors) == 1
    assert "Line coverage" in errors[0]
    assert "89.90%" in errors[0]
    assert "90.00%" in errors[0]


def test_coverage_floor_reports_branch_rate_below_threshold(
    tmp_path: Path,
    coverage_floor_module: ModuleType,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text('<coverage line-rate="0.95" branch-rate="0.809" />', encoding="utf-8")

    errors = coverage_floor_module.check_coverage_floor(coverage_xml, 90.0, 81.0)

    assert len(errors) == 1
    assert "Branch coverage" in errors[0]
    assert "80.90%" in errors[0]
    assert "81.00%" in errors[0]


def test_coverage_floor_reports_both_failed_floors(
    tmp_path: Path,
    coverage_floor_module: ModuleType,
) -> None:
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text('<coverage line-rate="0.899" branch-rate="0.809" />', encoding="utf-8")

    errors = coverage_floor_module.check_coverage_floor(coverage_xml, 90.0, 81.0)

    assert len(errors) == 2
    assert errors[0].startswith("Line coverage")
    assert errors[1].startswith("Branch coverage")
