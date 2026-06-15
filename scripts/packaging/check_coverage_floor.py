"""Fail when coverage.xml falls below the configured line coverage floor."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_COVERAGE_XML = Path("coverage.xml")
DEFAULT_MIN_LINE_PERCENT = 90.0


def coverage_line_percent(path: Path = DEFAULT_COVERAGE_XML) -> float:
    root = ET.parse(path).getroot()
    return float(root.attrib["line-rate"]) * 100.0


def check_coverage_floor(
    path: Path = DEFAULT_COVERAGE_XML,
    min_line_percent: float = DEFAULT_MIN_LINE_PERCENT,
) -> str | None:
    actual = coverage_line_percent(path)
    if actual < min_line_percent:
        return (
            f"Line coverage {actual:.2f}% is below the required "
            f"{min_line_percent:.2f}% floor"
        )
    return None


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
    args = parser.parse_args(argv)

    error = check_coverage_floor(args.coverage_xml, args.min_line)
    actual = coverage_line_percent(args.coverage_xml)
    if error is not None:
        print(error, file=sys.stderr)
        return 1
    print(f"Line coverage {actual:.2f}% meets the required {args.min_line:.2f}% floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
