"""Fail when coverage.xml falls below the configured coverage floors."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

DEFAULT_COVERAGE_XML = Path("coverage.xml")
DEFAULT_FLOOR_JSON = Path("tests/fixtures/coverage/coverage-floor.json")
SCHEMA_VERSION = 1


def coverage_line_percent(path: Path = DEFAULT_COVERAGE_XML) -> float:
    root = ET.parse(path).getroot()
    return float(root.attrib["line-rate"]) * 100.0


def coverage_branch_percent(path: Path = DEFAULT_COVERAGE_XML) -> float:
    root = ET.parse(path).getroot()
    return float(root.attrib["branch-rate"]) * 100.0


def load_coverage_floor(path: Path = DEFAULT_FLOOR_JSON) -> tuple[float, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported coverage floor schema_version {payload.get('schema_version')!r}"
        )
    return (
        _percent_field(payload, "line_percent"),
        _percent_field(payload, "branch_percent"),
    )


def check_coverage_floor(
    path: Path = DEFAULT_COVERAGE_XML,
    min_line_percent: float | None = None,
    min_branch_percent: float | None = None,
    floor_path: Path = DEFAULT_FLOOR_JSON,
) -> list[str]:
    floor_line_percent, floor_branch_percent = load_coverage_floor(floor_path)
    min_line = floor_line_percent if min_line_percent is None else min_line_percent
    min_branch = floor_branch_percent if min_branch_percent is None else min_branch_percent
    errors: list[str] = []
    line_actual = coverage_line_percent(path)
    if line_actual < min_line:
        errors.append(
            f"Line coverage {line_actual:.2f}% is below the required {min_line:.2f}% floor"
        )
    branch_actual = coverage_branch_percent(path)
    if branch_actual < min_branch:
        errors.append(
            f"Branch coverage {branch_actual:.2f}% is below the required {min_branch:.2f}% floor"
        )
    return errors


def _percent_field(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    if not isinstance(value, int | float):
        raise ValueError(f"coverage floor {field} must be a number")
    return float(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "coverage_xml",
        nargs="?",
        type=Path,
        default=DEFAULT_COVERAGE_XML,
        help="Path to coverage.py XML output.",
    )
    parser.add_argument(
        "--min-line",
        type=float,
        default=None,
        help="Minimum total line coverage percentage. Defaults to the committed floor.",
    )
    parser.add_argument(
        "--min-branch",
        type=float,
        default=None,
        help="Minimum total branch coverage percentage. Defaults to the committed floor.",
    )
    parser.add_argument(
        "--floor",
        type=Path,
        default=DEFAULT_FLOOR_JSON,
        help="Path to the committed coverage floor JSON.",
    )
    args = parser.parse_args(argv)

    try:
        floor_line_percent, floor_branch_percent = load_coverage_floor(args.floor)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Coverage floor check failed: {exc}", file=sys.stderr)
        return 1
    min_line = floor_line_percent if args.min_line is None else args.min_line
    min_branch = floor_branch_percent if args.min_branch is None else args.min_branch

    errors = check_coverage_floor(
        args.coverage_xml,
        min_line,
        min_branch,
        floor_path=args.floor,
    )
    line_actual = coverage_line_percent(args.coverage_xml)
    branch_actual = coverage_branch_percent(args.coverage_xml)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        f"Line coverage {line_actual:.2f}% meets the required {min_line:.2f}% floor; "
        f"branch coverage {branch_actual:.2f}% meets the required "
        f"{min_branch:.2f}% floor"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
