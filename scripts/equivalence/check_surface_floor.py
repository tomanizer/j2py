"""Fail when the equivalence-verified surface drops below its ratcheting floor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_REPORT_JSON = Path("corpus-reports/equivalence-surface.json")
DEFAULT_FLOOR_JSON = Path("tests/fixtures/equivalence/equivalence-surface-floor.json")
SCHEMA_VERSION = 1
COUNT_FIELDS = (
    "total_public_methods",
    "testable_public_methods",
    "verified_methods",
)
PERCENT_FIELDS = (
    "verified_public_surface_percent",
    "verified_testable_surface_percent",
)
EPSILON = 1e-12


def build_floor(report: dict[str, Any]) -> dict[str, Any]:
    """Extract the ratcheting floor payload from a surface report."""
    _validate_report(report)
    return {
        "schema_version": SCHEMA_VERSION,
        "description": (
            "Ratcheting floor for the equivalence-verified Java public method surface. "
            "Raise this file with scripts/equivalence/check_surface_floor.py "
            "--update-floor after adding passing equivalence tests."
        ),
        "summary": _floor_scope(report["summary"]),
        "libraries": [
            {"library": library["library"], **_floor_scope(library)}
            for library in sorted(report["libraries"], key=lambda item: str(item["library"]))
        ],
    }


def check_surface_floor(report: dict[str, Any], floor: dict[str, Any]) -> list[str]:
    """Return floor violations for an equivalence surface report."""
    try:
        _validate_report(report)
        _validate_floor(floor)
        errors: list[str] = []
        errors.extend(_check_scope("summary", report["summary"], floor["summary"]))
        libraries = {str(item["library"]): item for item in report["libraries"]}
        for floor_library in floor["libraries"]:
            library_name = str(floor_library["library"])
            actual = libraries.get(library_name)
            if actual is None:
                errors.append(f"library {library_name!r} is missing from the surface report")
                continue
            errors.extend(_check_scope(f"library {library_name}", actual, floor_library))
        return errors
    except ValueError as exc:
        return [str(exc)]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_floor(path: Path, report: dict[str, Any]) -> None:
    floor = build_floor(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(floor, indent=2, sort_keys=True) + "\n")


def _floor_scope(scope: dict[str, Any]) -> dict[str, int | float]:
    return {field: _int_field(scope, field) for field in COUNT_FIELDS} | {
        field: _float_field(scope, field) for field in PERCENT_FIELDS
    }


def _check_scope(name: str, actual: dict[str, Any], floor: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in COUNT_FIELDS:
        actual_value = _int_field(actual, field)
        floor_value = _int_field(floor, field)
        if actual_value < floor_value:
            errors.append(f"{name} {field} {actual_value} is below floor {floor_value}")
    for field in PERCENT_FIELDS:
        actual_value = _float_field(actual, field)
        floor_value = _float_field(floor, field)
        if actual_value + EPSILON < floor_value:
            errors.append(f"{name} {field} {actual_value:.6%} is below floor {floor_value:.6%}")
    return errors


def _validate_report(report: dict[str, Any]) -> None:
    if report.get("incomplete"):
        raise ValueError("equivalence surface report is incomplete because pytest failed")
    if report.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported equivalence surface report schema_version "
            f"{report.get('schema_version')!r}"
        )
    if not isinstance(report.get("summary"), dict):
        raise ValueError("equivalence surface report is missing summary")
    libraries = report.get("libraries")
    if not isinstance(libraries, list):
        raise ValueError("equivalence surface report is missing libraries")
    for library in libraries:
        if not isinstance(library, dict) or "library" not in library:
            raise ValueError("each report library entry must be an object with a library name")


def _validate_floor(floor: dict[str, Any]) -> None:
    if floor.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported equivalence surface floor schema_version {floor.get('schema_version')!r}"
        )
    if not isinstance(floor.get("summary"), dict):
        raise ValueError("equivalence surface floor is missing summary")
    libraries = floor.get("libraries")
    if not isinstance(libraries, list) or not libraries:
        raise ValueError("equivalence surface floor is missing libraries")
    for library in libraries:
        if not isinstance(library, dict) or "library" not in library:
            raise ValueError("each floor library entry must be an object with a library name")


def _int_field(scope: dict[str, Any], field: str) -> int:
    value = scope.get(field)
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _float_field(scope: dict[str, Any], field: str) -> float:
    value = scope.get(field)
    if not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    return float(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report_json",
        nargs="?",
        type=Path,
        default=DEFAULT_REPORT_JSON,
        help="Path to corpus-reports/equivalence-surface.json.",
    )
    parser.add_argument(
        "--floor",
        type=Path,
        default=DEFAULT_FLOOR_JSON,
        help="Path to the checked-in equivalence surface floor JSON.",
    )
    parser.add_argument(
        "--update-floor",
        action="store_true",
        help="Rewrite the floor file from the supplied report instead of checking it.",
    )
    args = parser.parse_args(argv)

    try:
        report = load_json(args.report_json)
        if args.update_floor:
            write_floor(args.floor, report)
            print(f"Updated equivalence surface floor at {args.floor}")
            return 0
        floor = load_json(args.floor)
        errors = check_surface_floor(report, floor)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Equivalence surface floor check failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("Equivalence surface floor check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    summary = report["summary"]
    print(
        "Equivalence surface "
        f"{summary['verified_methods']}/{summary['total_public_methods']} "
        f"({summary['verified_public_surface_percent']:.2%}) meets the committed floor"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
