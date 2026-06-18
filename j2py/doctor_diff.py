"""Comparison helpers for doctor assessment payloads."""

from __future__ import annotations

from typing import Any

from j2py.doctor_models import DoctorAssessment, DoctorDiff


def diff_assessments(before: DoctorAssessment, after: DoctorAssessment) -> DoctorDiff:
    before_payload = before.payload
    after_payload = after.payload
    before_files = _files_by_path(before_payload)
    after_files = _files_by_path(after_payload)
    before_unresolved = _imports_by_name(before_payload.get("unresolved_imports", []))
    after_unresolved = _imports_by_name(after_payload.get("unresolved_imports", []))
    before_warnings = _diagnostic_keys(before_files, "semantic_warnings")
    after_warnings = _diagnostic_keys(after_files, "semantic_warnings")
    before_unhandled = _diagnostic_keys(before_files, "unhandled")
    after_unhandled = _diagnostic_keys(after_files, "unhandled")
    before_unresolved_keys = set(before_unresolved)
    after_unresolved_keys = set(after_unresolved)
    before_warning_keys = set(before_warnings)
    after_warning_keys = set(after_warnings)
    before_unhandled_keys = set(before_unhandled)
    after_unhandled_keys = set(after_unhandled)
    before_parse_failures = {path for path, item in before_files.items() if not item["parse_ok"]}
    after_parse_failures = {path for path, item in after_files.items() if not item["parse_ok"]}

    payload = {
        "schema_version": 1,
        "before_source": before_payload.get("source"),
        "after_source": after_payload.get("source"),
        "summary_delta": _summary_delta(
            before_payload.get("summary", {}),
            after_payload.get("summary", {}),
        ),
        "coverage_delta": (
            after_payload.get("summary", {}).get("average_rule_coverage", 0.0)
            - before_payload.get("summary", {}).get("average_rule_coverage", 0.0)
        ),
        "parse_failures": {
            "added": sorted(after_parse_failures - before_parse_failures),
            "removed": sorted(before_parse_failures - after_parse_failures),
        },
        "unresolved_imports": {
            "added": [
                after_unresolved[key]
                for key in sorted(after_unresolved_keys - before_unresolved_keys)
            ],
            "removed": [
                before_unresolved[key]
                for key in sorted(before_unresolved_keys - after_unresolved_keys)
            ],
        },
        "semantic_warnings": {
            "added": _diagnostic_entries(after_warnings, after_warning_keys - before_warning_keys),
            "removed": _diagnostic_entries(
                before_warnings,
                before_warning_keys - after_warning_keys,
            ),
        },
        "unhandled_diagnostics": {
            "added": _diagnostic_entries(
                after_unhandled,
                after_unhandled_keys - before_unhandled_keys,
            ),
            "removed": _diagnostic_entries(
                before_unhandled,
                before_unhandled_keys - after_unhandled_keys,
            ),
        },
        "file_changes": _file_changes(before_files, after_files),
    }
    return DoctorDiff(payload=payload)


def _files_by_path(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["path"]: item for item in payload.get("files", [])}


def _imports_by_name(imports: Any) -> dict[str, dict[str, Any]]:
    return {item["import"]: item for item in imports}


def _summary_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(before) | set(after))
    return {
        key: after.get(key, 0) - before.get(key, 0)
        for key in keys
        if isinstance(before.get(key, 0), (int, float))
        and isinstance(after.get(key, 0), (int, float))
    }


def _diagnostic_keys(
    files: dict[str, dict[str, Any]],
    diagnostic_key: str,
) -> dict[tuple[str, int | None, str, str, str], dict[str, Any]]:
    diagnostics: dict[tuple[str, int | None, str, str, str], dict[str, Any]] = {}
    for path, item in files.items():
        for diagnostic in item["translation"][diagnostic_key]:
            key = (
                path,
                diagnostic["line"],
                diagnostic["node_type"],
                diagnostic["reason"],
                diagnostic["text"],
            )
            diagnostics[key] = {"path": path, **diagnostic}
    return diagnostics


def _diagnostic_entries(
    diagnostics: dict[tuple[str, int | None, str, str, str], dict[str, Any]],
    keys: set[tuple[str, int | None, str, str, str]],
) -> list[dict[str, Any]]:
    return [diagnostics[key] for key in sorted(keys)]


def _file_changes(
    before_files: dict[str, dict[str, Any]],
    after_files: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    added = sorted(set(after_files) - set(before_files))
    removed = sorted(set(before_files) - set(after_files))
    changed: list[dict[str, Any]] = []
    for path in sorted(set(before_files) & set(after_files)):
        before = before_files[path]
        after = after_files[path]
        item = {
            "path": path,
            "parse_ok_changed": before["parse_ok"] != after["parse_ok"],
            "rule_coverage_delta": after["translation"]["rule_coverage"]
            - before["translation"]["rule_coverage"],
            "semantic_warnings_delta": len(after["translation"]["semantic_warnings"])
            - len(before["translation"]["semantic_warnings"]),
            "unhandled_delta": len(after["translation"]["unhandled"])
            - len(before["translation"]["unhandled"]),
            "unresolved_imports_delta": len(after["unresolved_imports"])
            - len(before["unresolved_imports"]),
        }
        if any(value for key, value in item.items() if key != "path"):
            changed.append(item)
    return {
        "added": [{"path": path} for path in added],
        "removed": [{"path": path} for path in removed],
        "changed": changed,
    }
