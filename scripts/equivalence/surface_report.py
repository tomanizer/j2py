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
from functools import lru_cache
from pathlib import Path
from typing import Any

from j2py.parse.java_ast import JavaNode, parse_file
from scripts.corpus.corpus_presets import get_preset

FIXTURE_ROOT = Path("tests/fixtures/equivalence")
SCHEMA_VERSION = 1
CHAR_OVERLOAD_REASON = "char/Character overload dispatch currently erases to Python str"
STRING_OVERLOAD_REASON = (
    "String/Character overload dispatch is outside the first literal-oracle surface"
)
FIXTURE_LIBRARIES = {
    "BooleanUtils.java": "commons-lang",
    "CharUtils.java": "commons-lang",
    "NumberUtils.java": "commons-lang",
    "StringUtils.java": "commons-lang",
    "GuavaPrecedenceMath.java": "guava",
    "Strings.java": "guava",
}
SYNTHETIC_FIXTURES = {
    "GuavaPrecedenceMath.java",
}
LIBRARY_PRESETS = {
    "commons-lang": "commons-lang-dense",
    "guava": "guava-dense",
}
LIBRARY_SOURCE_MODULES = {
    "commons-lang": ("src/main/java",),
    "guava": ("guava/src",),
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


@dataclass(frozen=True)
class LibrarySurface:
    library: str
    source_available: bool
    source_root: str | None
    source_preset: str
    total_public_methods: int | None
    source_files: int
    parse_error_files: int
    method_signatures: frozenset[str]


def build_report(passed_methods: Iterable[PassedMethod]) -> dict[str, Any]:
    """Return a JSON-serialisable equivalence surface report."""
    passed_by_fixture: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for method in passed_methods:
        passed_by_fixture[method.fixture][method.signature].add(method.nodeid)

    fixtures = sorted(path.name for path in FIXTURE_ROOT.glob("*.java"))
    fixture_reports: list[dict[str, Any]] = []
    totals = _empty_totals()
    library_totals: dict[str, dict[str, int]] = defaultdict(_empty_totals)
    verified_by_library: dict[str, set[str]] = defaultdict(set)
    for fixture in fixtures:
        public_methods = public_methods_for_fixture(FIXTURE_ROOT / fixture)
        public_signatures = {method.signature for method in public_methods}
        verified_set = set(passed_by_fixture[fixture]) & public_signatures
        verified = sorted(verified_set)
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
        if fixture not in SYNTHETIC_FIXTURES:
            verified_by_library[library].update(verified_set)
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

    library_surfaces = _library_surfaces()
    rendered_libraries: list[dict[str, Any]] = []
    library_wide_totals = _empty_library_totals()
    for library, counts in sorted(library_totals.items()):
        library_report: dict[str, Any] = {"library": library, **_with_percentages(counts)}
        surface = library_surfaces.get(library)
        if surface is None:
            library_report.update(_unavailable_library_surface())
        else:
            verified_library_methods = len(verified_by_library[library] & surface.method_signatures)
            library_report.update(
                {
                    "library_source_available": surface.source_available,
                    "library_source_root": surface.source_root,
                    "library_source_preset": surface.source_preset,
                    "library_source_files": surface.source_files,
                    "library_parse_error_files": surface.parse_error_files,
                    "library_total_public_methods": surface.total_public_methods,
                    "verified_library_methods": verified_library_methods
                    if surface.total_public_methods is not None
                    else None,
                    "verified_library_surface_percent": _percent(
                        verified_library_methods, surface.total_public_methods or 0
                    )
                    if surface.total_public_methods is not None
                    else None,
                }
            )
            if surface.total_public_methods is not None:
                library_wide_totals["library_total_public_methods"] += surface.total_public_methods
                library_wide_totals["verified_library_methods"] += verified_library_methods
                library_wide_totals["library_source_files"] += surface.source_files
                library_wide_totals["library_parse_error_files"] += surface.parse_error_files
                library_wide_totals["library_sources_available"] += int(surface.source_available)
        rendered_libraries.append(library_report)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "metric_definition": {
            "verified_public_surface_percent": (
                "fixture-scoped public Java method signatures with at least one passing "
                "literal-oracle pytest item divided by total public Java method "
                "signatures in the measured equivalence fixtures"
            ),
            "verified_testable_surface_percent": (
                "same numerator divided by total public signatures minus explicitly "
                "untestable signatures"
            ),
            "verified_library_surface_percent": (
                "verified non-synthetic fixture method signatures present in the pinned "
                "library checkout divided by total public Java method signatures in the "
                "actual pinned library source roots"
            ),
        },
        "summary": _with_percentages(totals),
        "library_wide_summary": _with_library_percentages(library_wide_totals),
        "libraries": rendered_libraries,
        "fixtures": fixture_reports,
    }


def public_methods_for_fixture(path: Path) -> list[PublicMethod]:
    parsed = parse_file(path)
    return _public_methods_for_node(parsed.root, fallback_class_name=path.stem)


def _public_methods_for_node(
    node: JavaNode,
    *,
    fallback_class_name: str,
    class_name: str | None = None,
    implicit_public_methods: bool = False,
) -> list[PublicMethod]:
    methods: list[PublicMethod] = []
    current_class = class_name
    current_implicit_public = implicit_public_methods
    if node.type in {
        "class_declaration",
        "enum_declaration",
        "interface_declaration",
        "annotation_type_declaration",
    }:
        name_node = node.child_by_field("name")
        node_name = name_node.text if name_node is not None else fallback_class_name
        current_class = f"{class_name}.{node_name}" if class_name else node_name
        current_implicit_public = node.type in {
            "interface_declaration",
            "annotation_type_declaration",
        }

    if node.type == "method_declaration":
        modifiers = next((child.text for child in node.children if child.type == "modifiers"), "")
        modifier_words = set(modifiers.split())
        is_public = "public" in modifier_words or (
            current_implicit_public and "private" not in modifier_words
        )
        if not is_public:
            return methods
        name_node = node.child_by_field("name")
        if name_node is None:
            return methods
        name = name_node.text
        owner = current_class or fallback_class_name
        signature = f"{owner}.{name}({','.join(_parameter_types(node))})"
        methods.append(
            PublicMethod(
                fixture=fallback_class_name,
                class_name=owner,
                name=name,
                signature=signature,
                line=node.location.line,
            )
        )
        return methods

    for child in node.named_children:
        methods.extend(
            _public_methods_for_node(
                child,
                fallback_class_name=fallback_class_name,
                class_name=current_class,
                implicit_public_methods=current_implicit_public,
            )
        )
    return methods


def render_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    library_summary = report["library_wide_summary"]
    fixture_count = len(report["fixtures"])
    lines = [
        f"Equivalence-verified fixture surface ({fixture_count} files)",
        "",
        "Fixture surface by library",
        "",
        "| Library | Verified fixture / fixture public | Fixture public surface | "
        "Verified / testable | Untestable |",
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
            "Library-wide denominator",
            "",
            "| Library | Verified library methods | Library public methods | "
            "Library-wide surface | Source |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for library in report["libraries"]:
        lines.append(_render_library_wide_row(library))
    lines.extend(
        [
            "| **Total** | {verified} | {total} | {percent} | {source} |".format(
                verified=library_summary["verified_library_methods"],
                total=library_summary["library_total_public_methods"],
                percent=_format_optional_percent(
                    library_summary["verified_library_surface_percent"]
                ),
                source=_format_library_summary_source(library_summary),
            ),
            "",
            "By fixture",
            "",
            "| Fixture | Verified / fixture public | Fixture public surface | "
            "Verified / testable | Untestable |",
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
            "Metric: fixture surface is public Java method signatures in the measured "
            "equivalence fixtures with at least one passing literal-oracle pytest item. "
            "Library-wide surface uses the same non-synthetic verified methods over the "
            "public method denominator in the pinned source library roots.",
        ]
    )
    return "\n".join(lines)


@lru_cache(maxsize=1)
def _library_surfaces() -> dict[str, LibrarySurface]:
    return {
        library: _library_surface(library, preset_name)
        for library, preset_name in LIBRARY_PRESETS.items()
    }


def _library_surface(library: str, preset_name: str) -> LibrarySurface:
    preset = get_preset(preset_name)
    repo_path = preset.repo_path
    if not repo_path.exists():
        return LibrarySurface(
            library=library,
            source_available=False,
            source_root=None,
            source_preset=preset.name,
            total_public_methods=None,
            source_files=0,
            parse_error_files=0,
            method_signatures=frozenset(),
        )

    files = list(
        _library_java_files(
            repo_path,
            LIBRARY_SOURCE_MODULES.get(library, preset.modules),
            preset.exclude_paths,
        )
    )
    methods: list[PublicMethod] = []
    parse_error_files = 0
    for path in files:
        parsed = parse_file(path)
        if parsed.has_errors:
            parse_error_files += 1
        methods.extend(_public_methods_for_node(parsed.root, fallback_class_name=path.stem))

    return LibrarySurface(
        library=library,
        source_available=True,
        source_root=str(repo_path),
        source_preset=preset.name,
        total_public_methods=len(methods),
        source_files=len(files),
        parse_error_files=parse_error_files,
        method_signatures=frozenset(method.signature for method in methods),
    )


def _library_java_files(
    repo_path: Path,
    modules: Iterable[str],
    exclude_paths: Iterable[str],
) -> Iterable[Path]:
    excluded = set(exclude_paths)
    for module in modules:
        module_path = repo_path / module
        if not module_path.exists():
            continue
        for path in sorted(module_path.rglob("*.java")):
            relative = path.relative_to(repo_path).as_posix()
            if relative in excluded:
                continue
            yield path


def _render_library_wide_row(library: dict[str, Any]) -> str:
    return "| {library} | {verified} | {total} | {percent} | {source} |".format(
        library=library["library"],
        verified=_format_optional_count(library["verified_library_methods"]),
        total=_format_optional_count(library["library_total_public_methods"]),
        percent=_format_optional_percent(library["verified_library_surface_percent"]),
        source=_format_library_source(library),
    )


def _unavailable_library_surface() -> dict[str, Any]:
    return {
        "library_source_available": False,
        "library_source_root": None,
        "library_source_preset": "unknown",
        "library_source_files": 0,
        "library_parse_error_files": 0,
        "library_total_public_methods": None,
        "verified_library_methods": None,
        "verified_library_surface_percent": None,
    }


def _format_library_source(library: dict[str, Any]) -> str:
    if not library["library_source_available"]:
        return f"{library['library_source_preset']} checkout unavailable"
    details = (
        f"{library['library_source_preset']} checkout, {library['library_source_files']} files"
    )
    if library["library_parse_error_files"]:
        details += f", {library['library_parse_error_files']} parse-error files"
    return details


def _format_library_summary_source(summary: dict[str, Any]) -> str:
    available = summary["library_sources_available"]
    total = len(LIBRARY_PRESETS)
    if available == total:
        return "all pinned checkouts"
    if available == 0:
        return "library checkouts unavailable"
    return f"{available}/{total} pinned checkouts"


def _format_optional_count(value: Any) -> str:
    return "n/a" if value is None else str(value)


def _format_optional_percent(value: Any) -> str:
    return "n/a" if value is None else f"{value:.1%}"


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


def _empty_library_totals() -> dict[str, int]:
    return {
        "library_total_public_methods": 0,
        "verified_library_methods": 0,
        "library_source_files": 0,
        "library_parse_error_files": 0,
        "library_sources_available": 0,
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


def _with_library_percentages(counts: dict[str, int]) -> dict[str, int | float | None]:
    total = counts["library_total_public_methods"]
    return {
        **counts,
        "verified_library_surface_percent": _percent(counts["verified_library_methods"], total)
        if total
        else None,
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
