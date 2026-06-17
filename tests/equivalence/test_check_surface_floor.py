"""Tests for the equivalence surface ratchet."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.equivalence.check_surface_floor import (
    build_floor,
    check_surface_floor,
    main,
)
from scripts.equivalence.surface_report import PassedMethod, build_report


def test_check_surface_floor_accepts_matching_floor() -> None:
    report = build_report(
        [
            PassedMethod(
                fixture="CharUtils.java",
                signature="CharUtils.compare(char,char)",
                nodeid="test_char_utils.py::test_compare",
            ),
            PassedMethod(
                fixture="GuavaPrecedenceMath.java",
                signature="GuavaPrecedenceMath.expandedCapacity(int)",
                nodeid="test_guava.py::test_expanded_capacity",
            ),
        ]
    )
    floor = build_floor(report)

    assert check_surface_floor(report, floor) == []


def test_check_surface_floor_rejects_verified_count_regression() -> None:
    floor_report = build_report(
        [
            PassedMethod(
                fixture="CharUtils.java",
                signature="CharUtils.compare(char,char)",
                nodeid="test_char_utils.py::test_compare",
            ),
            PassedMethod(
                fixture="GuavaPrecedenceMath.java",
                signature="GuavaPrecedenceMath.expandedCapacity(int)",
                nodeid="test_guava.py::test_expanded_capacity",
            ),
        ]
    )
    degraded_report = build_report(
        [
            PassedMethod(
                fixture="CharUtils.java",
                signature="CharUtils.compare(char,char)",
                nodeid="test_char_utils.py::test_compare",
            ),
        ]
    )

    errors = check_surface_floor(degraded_report, build_floor(floor_report))

    assert "summary verified_methods 1 is below floor 2" in errors
    assert any("summary verified_public_surface_percent" in error for error in errors)
    assert "library guava verified_methods 0 is below floor 1" in errors


def test_check_surface_floor_rejects_incomplete_report() -> None:
    errors = check_surface_floor(
        {"schema_version": 1, "incomplete": True},
        {"schema_version": 1, "summary": {}, "libraries": [{"library": "commons-lang"}]},
    )

    assert errors == ["equivalence surface report is incomplete because pytest failed"]


def test_check_surface_floor_rejects_malformed_report_libraries() -> None:
    errors = check_surface_floor(
        {
            "schema_version": 1,
            "summary": {
                "total_public_methods": 1,
                "testable_public_methods": 1,
                "verified_methods": 1,
                "verified_public_surface_percent": 1.0,
                "verified_testable_surface_percent": 1.0,
            },
            "libraries": [{}],
        },
        {
            "schema_version": 1,
            "summary": {
                "total_public_methods": 1,
                "testable_public_methods": 1,
                "verified_methods": 1,
                "verified_public_surface_percent": 1.0,
                "verified_testable_surface_percent": 1.0,
            },
            "libraries": [{"library": "commons-lang"}],
        },
    )

    assert errors == ["each report library entry must be an object with a library name"]


def test_update_floor_cli_writes_report_floor(tmp_path: Path) -> None:
    report = build_report(
        [
            PassedMethod(
                fixture="NumberUtils.java",
                signature="NumberUtils.toInt(String)",
                nodeid="test_number_utils.py::test_to_int",
            ),
        ]
    )
    report_path = tmp_path / "report.json"
    floor_path = tmp_path / "floor.json"
    report_path.write_text(json.dumps(report))

    assert main([str(report_path), "--floor", str(floor_path), "--update-floor"]) == 0

    floor = json.loads(floor_path.read_text())
    assert floor["summary"]["verified_methods"] == 1
    assert floor["libraries"][0]["library"] == "commons-lang"
