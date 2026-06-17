"""Fail when coverage.xml falls below the configured coverage floors."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_COVERAGE_XML = Path("coverage.xml")
DEFAULT_MIN_LINE_PERCENT = 90.0
DEFAULT_MIN_BRANCH_PERCENT = 81.0


def coverage_line_percent(path: Path = DEFAULT_COVERAGE_XML) -> float:
    root = ET.parse(path).getroot()
    return float(root.attrib["line-rate"]) * 100.0


def coverage_branch_percent(path: Path = DEFAULT_COVERAGE_XML) -> float:
    root = ET.parse(path).getroot()
    return float(root.attrib["branch-rate"]) * 100.0


def check_coverage_floor(
    path: Path = DEFAULT_COVERAGE_XML,
    min_line_percent: float = DEFAULT_MIN_LINE_PERCENT,
    min_branch_percent: float = DEFAULT_MIN_BRANCH_PERCENT,
) -> list[str]:
    errors: list[str] = []
    line_actual = coverage_line_percent(path)
    if line_actual < min_line_percent:
        errors.append(
            f"Line coverage {line_actual:.2f}% is below the required {min_line_percent:.2f}% floor"
        )
    branch_actual = coverage_branch_percent(path)
    if branch_actual < min_branch_percent:
        errors.append(
            f"Branch coverage {branch_actual:.2f}% is below the required "
            f"{min_branch_percent:.2f}% floor"
        )
    return errors


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
        default=DEFAULT_MIN_LINE_PERCENT,
        help="Minimum total line coverage percentage.",
    )
    parser.add_argument(
        "--min-branch",
        type=float,
        default=DEFAULT_MIN_BRANCH_PERCENT,
        help="Minimum total branch coverage percentage.",
    )
    args = parser.parse_args(argv)

    errors = check_coverage_floor(args.coverage_xml, args.min_line, args.min_branch)
    line_actual = coverage_line_percent(args.coverage_xml)
    branch_actual = coverage_branch_percent(args.coverage_xml)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        f"Line coverage {line_actual:.2f}% meets the required {args.min_line:.2f}% floor; "
        f"branch coverage {branch_actual:.2f}% meets the required "
        f"{args.min_branch:.2f}% floor"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
