"""Build and render the equivalence-verified surface report.

The pytest collector writes methods exercised by passing literal-oracle tests. This
module joins that dynamic evidence with the Java fixture method surface so the report is
based on the current test outcome, not on a static checklist.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from j2py.parse.java_ast import JavaNode, parse_file

FIXTURE_ROOT = Path("tests/fixtures/equivalence")
SCHEMA_VERSION = 1
CHAR_OVERLOAD_REASON = "char/Character overload dispatch currently erases to Python str"
STRING_OVERLOAD_REASON = (
    "String/Character overload dispatch is outside the first literal-oracle surface"
)
FIXTURE_LIBRARIES = {
    "CharUtils.java": "commons-lang",
    "NumberUtils.java": "commons-lang",
    "StringUtils.java": "commons-lang",
    "GuavaPrecedenceMath.java": "guava",
}

EXPLICIT_UNTESTABLE_REASONS: dict[str, dict[str, str]] = {
    "CharUtils.java": {
        "CharUtils.toChar(Character)": CHAR_OVERLOAD_REASON,
        "CharUtils.toChar(Character,char)": CHAR_OVERLOAD_REASON,
        "CharUtils.toChar(String)": STRING_OVERLOAD_REASON,
        "CharUtils.toChar(String,char)": STRING_OVERLOAD_REASON,
        "CharUtils.toCharacterObject(char)": CHAR_OVERLOAD_REASON,
        "CharUtils.toCharacterObject(String)": STRING_OVERLOAD_REASON,
        "CharUtils.toIntValue(char)": CHAR_OVERLOAD_REASON,
        "CharUtils.toIntValue(char,int)": CHAR_OVERLOAD_REASON,
        "CharUtils.toIntValue(Character)": CHAR_OVERLOAD_REASON,
        "CharUtils.toIntValue(Character,int)": CHAR_OVERLOAD_REASON,
        "CharUtils.toString(char)": CHAR_OVERLOAD_REASON,
        "CharUtils.toString(Character)": CHAR_OVERLOAD_REASON,
        "CharUtils.unicodeEscaped(char)": CHAR_OVERLOAD_REASON,
        "CharUtils.unicodeEscaped(Character)": CHAR_OVERLOAD_REASON,
    },
}


@dataclass(frozen=True)
class PassedMethod:
    fixture: str
    signature: str
    nodeid: str


@dataclass(frozen=True)
class PublicMethod:
    fixture: str
    class_name: str
    name: str
    signature: str
    line: int


def build_report(passed_methods: Iterable[PassedMethod]) -> dict[str, Any]:
    """Return a JSON-serialisable equivalence surface report."""
    passed_by_fixture: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for method in passed_methods:
        passed_by_fixture[method.fixture][method.signature].add(method.nodeid)

    fixtures = sorted(path.name for path in FIXTURE_ROOT.glob("*.java"))
    fixture_reports: list[dict[str, Any]] = []
    totals = _empty_totals()
    library_totals: dict[str, dict[str, int]] = defaultdict(_empty_totals)
    for fixture in fixtures:
        public_methods = public_methods_for_fixture(FIXTURE_ROOT / fixture)
        public_signatures = {method.signature for method in public_methods}
        verified = sorted(set(passed_by_fixture[fixture]) & public_signatures)
        verified_set = set(verified)
        untestable = {
            signature: reason
            for signature, reason in EXPLICIT_UNTESTABLE_REASONS.get(fixture, {}).items()
            if signature in public_signatures and signature not in verified_set
        }
        testable_count = len(public_methods) - len(untestable)
        unverified = sorted(
            signature
            for signature in public_signatures
            if signature not in verified_set and signature not in untestable
        )
        library = FIXTURE_LIBRARIES.get(fixture, "unknown")
        fixture_report = {
            "fixture": fixture,
            "library": library,
            "total_public_methods": len(public_methods),
            "testable_public_methods": testable_count,
            "verified_methods": len(verified),
            "verified_public_surface_percent": _percent(len(verified), len(public_methods)),
            "verified_testable_surface_percent": _percent(len(verified), testable_count),
            "untestable_methods": len(untestable),
            "unverified_methods": len(unverified),
            "verified_method_signatures": verified,
            "untestable_method_reasons": dict(sorted(untestable.items())),
            "unverified_method_signatures": unverified,
            "passing_assertion_tests": {
                signature: sorted(passed_by_fixture[fixture][signature]) for signature in verified
            },
        }
        fixture_reports.append(fixture_report)
        _add_counts(
            totals,
            total_public_methods=len(public_methods),
            verified_methods=len(verified),
            untestable_methods=len(untestable),
            testable_public_methods=testable_count,
        )
        _add_counts(
            library_totals[library],
            total_public_methods=len(public_methods),
            verified_methods=len(verified),
            untestable_methods=len(untestable),
            testable_public_methods=testable_count,
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "metric_definition": {
            "verified_public_surface_percent": (
                "public Java method signatures with at least one passing literal-oracle "
                "pytest item divided by total public Java method signatures"
            ),
            "verified_testable_surface_percent": (
                "same numerator divided by total public signatures minus explicitly "
                "untestable signatures"
            ),
        },
        "summary": _with_percentages(totals),
        "libraries": [
            {"library": library, **_with_percentages(counts)}
            for library, counts in sorted(library_totals.items())
        ],
        "fixtures": fixture_reports,
    }


def public_methods_for_fixture(path: Path) -> list[PublicMethod]:
    parsed = parse_file(path)
    methods: list[PublicMethod] = []
    class_name = path.stem
    for node in parsed.root.find_all("method_declaration"):
        modifiers = next((child.text for child in node.children if child.type == "modifiers"), "")
        if "public" not in modifiers.split():
            continue
        name_node = node.child_by_field("name")
        if name_node is None:
            continue
        name = name_node.text
        signature = f"{class_name}.{name}({','.join(_parameter_types(node))})"
        methods.append(
            PublicMethod(
                fixture=path.name,
                class_name=class_name,
                name=name,
                signature=signature,
                line=node.location.line,
            )
        )
    return methods


def render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Equivalence-verified surface",
        "",
        "By library",
        "",
        "| Library | Verified / public | Public surface | Verified / testable | Untestable |",
        "|---|---:|---:|---:|---:|",
    ]
    for library in report["libraries"]:
        lines.append(
            "| {library} | {verified_methods}/{total_public_methods} | {public:.1%} | "
            "{verified_methods}/{testable_public_methods} ({testable:.1%}) | "
            "{untestable_methods} |".format(
                **library,
                public=library["verified_public_surface_percent"],
                testable=library["verified_testable_surface_percent"],
            )
        )
    lines.extend(
        [
            "| **Total** | {verified_methods}/{total_public_methods} | {public:.1%} | "
            "{verified_methods}/{testable_public_methods} ({testable:.1%}) | "
            "{untestable_methods} |".format(
                **summary,
                public=summary["verified_public_surface_percent"],
                testable=summary["verified_testable_surface_percent"],
            ),
            "",
            "By fixture",
            "",
            "| Fixture | Verified / public | Public surface | Verified / testable | Untestable |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for fixture in report["fixtures"]:
        lines.append(
            "| {fixture} | {verified_methods}/{total_public_methods} | {public:.1%} | "
            "{verified_methods}/{testable_public_methods} ({testable:.1%}) | "
            "{untestable_methods} |".format(
                **fixture,
                public=fixture["verified_public_surface_percent"],
                testable=fixture["verified_testable_surface_percent"],
            )
        )
    lines.extend(
        [
            "| **Total** | {verified_methods}/{total_public_methods} | {public:.1%} | "
            "{verified_methods}/{testable_public_methods} ({testable:.1%}) | "
            "{untestable_methods} |".format(
                **summary,
                public=summary["verified_public_surface_percent"],
                testable=summary["verified_testable_surface_percent"],
            ),
            "",
            "Metric: public Java method signatures with at least one passing literal-oracle "
            "pytest item.",
        ]
    )
    return "\n".join(lines)


def write_report(path: Path, passed_methods: Iterable[PassedMethod]) -> dict[str, Any]:
    report = build_report(passed_methods)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def load_passed_methods(path: Path) -> list[PassedMethod]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") == SCHEMA_VERSION and "fixtures" in payload:
        passed: list[PassedMethod] = []
        for fixture in payload["fixtures"]:
            fixture_name = fixture["fixture"]
            for signature, nodeids in fixture.get("passing_assertion_tests", {}).items():
                passed.extend(
                    PassedMethod(fixture=fixture_name, signature=signature, nodeid=nodeid)
                    for nodeid in nodeids
                )
        return passed
    return [PassedMethod(**item) for item in payload.get("passed_methods", [])]


def _parameter_types(method_node: JavaNode) -> list[str]:
    params = next(
        (child for child in method_node.children if child.type == "formal_parameters"),
        None,
    )
    if params is None:
        return []
    result: list[str] = []
    for param in params.named_children:
        if param.type not in {"formal_parameter", "spread_parameter"}:
            continue
        type_node = _first_type_child(param)
        if type_node is None:
            continue
        suffix = "..." if param.type == "spread_parameter" else ""
        result.append(_compact_type(type_node.text) + suffix)
    return result


def _first_type_child(param: JavaNode) -> JavaNode | None:
    for child in param.named_children:
        if child.type in {"modifiers", "variable_declarator", "identifier"}:
            continue
        return child
    return None


def _compact_type(text: str) -> str:
    return "".join(text.split())


def _percent(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _empty_totals() -> dict[str, int]:
    return {
        "total_public_methods": 0,
        "verified_methods": 0,
        "untestable_methods": 0,
        "testable_public_methods": 0,
    }


def _add_counts(
    totals: dict[str, int],
    *,
    total_public_methods: int,
    verified_methods: int,
    untestable_methods: int,
    testable_public_methods: int,
) -> None:
    totals["total_public_methods"] += total_public_methods
    totals["verified_methods"] += verified_methods
    totals["untestable_methods"] += untestable_methods
    totals["testable_public_methods"] += testable_public_methods


def _with_percentages(counts: dict[str, int]) -> dict[str, int | float]:
    return {
        **counts,
        "verified_public_surface_percent": _percent(
            counts["verified_methods"], counts["total_public_methods"]
        ),
        "verified_testable_surface_percent": _percent(
            counts["verified_methods"], counts["testable_public_methods"]
        ),
        "unverified_methods": (
            counts["total_public_methods"]
            - counts["verified_methods"]
            - counts["untestable_methods"]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="JSON artifact written by pytest collection")
    parser.add_argument(
        "--write-json",
        type=Path,
        help="Optional path for a normalised report JSON. Defaults to updating artifact.",
    )
    args = parser.parse_args()

    passed_methods = load_passed_methods(args.artifact)
    output = args.write_json or args.artifact
    report = write_report(output, passed_methods)
    print(render_report(report))


if __name__ == "__main__":
    main()
