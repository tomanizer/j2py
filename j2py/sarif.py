"""SARIF export for j2py diagnostic artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from j2py.doctor import DoctorAssessment, load_assessment_json

SARIF_SCHEMA_URL = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"


@dataclass(frozen=True)
class SarifReport:
    """JSON-serialisable SARIF report."""

    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(self.payload, indent=2, sort_keys=True) + "\n"


RULES: dict[str, dict[str, str]] = {
    "j2py.parse-error": {
        "name": "Java parse error",
        "shortDescription": "Java source could not be parsed cleanly.",
        "help": "Fix the Java syntax before relying on translation diagnostics for this file.",
    },
    "j2py.unhandled-construct": {
        "name": "Unhandled Java construct",
        "shortDescription": "The deterministic rule layer did not fully translate this construct.",
        "help": "Add rule-layer support or plan manual migration for this construct.",
    },
    "j2py.semantic-warning": {
        "name": "Semantic warning",
        "shortDescription": "j2py translated this construct but Java/Python behavior needs review.",
        "help": "Review the translated Python against the Java source for semantic equivalence.",
    },
    "j2py.todo": {
        "name": "Manual port marker",
        "shortDescription": "Generated output contains a j2py TODO/manual-port marker.",
        "help": "Resolve the manual-port marker before treating the translation as complete.",
    },
    "j2py.validation.syntax": {
        "name": "Python syntax validation failure",
        "shortDescription": "Generated Python failed syntax validation.",
        "help": "Inspect the generated Python and the source construct that produced it.",
    },
    "j2py.validation.ruff": {
        "name": "Ruff validation failure",
        "shortDescription": "Generated Python failed ruff validation.",
        "help": "Inspect the ruff diagnostic and generated Python.",
    },
    "j2py.validation.mypy": {
        "name": "Mypy validation failure",
        "shortDescription": "Generated Python failed mypy validation.",
        "help": "Inspect the mypy diagnostic and generated Python.",
    },
    "j2py.validation": {
        "name": "Python validation failure",
        "shortDescription": "Generated Python failed validation.",
        "help": "Inspect the validation diagnostic and generated Python.",
    },
    "j2py.unresolved-import": {
        "name": "Unresolved import boundary",
        "shortDescription": (
            "Java import is not covered by defaults, config, or scanned project declarations."
        ),
        "help": (
            "Review whether this import needs import_map, type_map, a stub, a plugin, "
            "or manual porting."
        ),
    },
}

_PATH_LINE_RE = re.compile(r"^(?P<path>.*?):(?P<line>\d+)(?::\d+)?:")
_SYNTAX_LINE_RE = re.compile(r"line (?P<line>\d+)")


def load_sarif_assessment(path: Path) -> DoctorAssessment:
    return load_assessment_json(path)


def assessment_to_sarif(assessment: DoctorAssessment) -> SarifReport:
    payload = assessment.payload
    results = sorted(
        _assessment_results(payload),
        key=lambda item: (
            item["ruleId"],
            item["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
            item["locations"][0]["physicalLocation"].get("region", {}).get("startLine", 0),
            item["message"]["text"],
        ),
    )
    sarif = {
        "$schema": SARIF_SCHEMA_URL,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "j2py",
                        "informationUri": "https://github.com/tomanizer/j2py",
                        "rules": [_rule_descriptor(rule_id) for rule_id in sorted(RULES)],
                    }
                },
                "results": results,
            }
        ],
    }
    return SarifReport(payload=sarif)


def write_sarif(path: Path, report: SarifReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json(), encoding="utf-8")


def _assessment_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for file_payload in payload.get("files", []):
        path = str(file_payload["path"])
        results.extend(_parse_error_results(path, file_payload))
        results.extend(_diagnostic_results(path, file_payload, "semantic_warnings"))
        results.extend(_diagnostic_results(path, file_payload, "unhandled"))
        results.extend(_todo_results(path, file_payload))
        results.extend(_validation_results(path, file_payload))
        results.extend(_unresolved_import_results(path, file_payload))
    return results


def _parse_error_results(path: str, file_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _result(
            "j2py.parse-error",
            "error",
            path,
            error.get("line"),
            f"{error['reason']}: {error['node_type']} {error['text']}",
        )
        for error in file_payload.get("parse_errors", [])
    ]


def _diagnostic_results(
    path: str,
    file_payload: dict[str, Any],
    diagnostic_key: str,
) -> list[dict[str, Any]]:
    rule_id = (
        "j2py.semantic-warning"
        if diagnostic_key == "semantic_warnings"
        else "j2py.unhandled-construct"
    )
    return [
        _result(
            rule_id,
            "warning",
            path,
            diagnostic.get("line"),
            f"{diagnostic['reason']}: {diagnostic['node_type']} {diagnostic['text']}",
        )
        for diagnostic in file_payload.get("translation", {}).get(diagnostic_key, [])
    ]


def _todo_results(path: str, file_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _result("j2py.todo", "warning", path, None, todo)
        for todo in file_payload.get("translation", {}).get("todos", [])
    ]


def _validation_results(path: str, file_payload: dict[str, Any]) -> list[dict[str, Any]]:
    validation = file_payload.get("translation", {}).get("validation")
    if not validation:
        return []
    results = []
    for error in validation.get("errors", []):
        rule_id = _validation_rule_id(str(error), validation)
        generated_path, line = _validation_location(str(error), path)
        results.append(
            _result(rule_id, _validation_level(rule_id), generated_path, line, str(error))
        )
    return results


def _unresolved_import_results(path: str, file_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _result(
            "j2py.unresolved-import",
            "warning",
            path,
            None,
            f"{item['import']} ({item['category']}): {item['reason']}",
        )
        for item in file_payload.get("unresolved_imports", [])
    ]


def _validation_rule_id(error: str, validation: dict[str, Any]) -> str:
    if not validation.get("syntax_ok", True) or error.startswith("SyntaxError:"):
        return "j2py.validation.syntax"
    if ": error:" in error:
        return "j2py.validation.mypy"
    if re.search(r": [EF]\d+", error):
        return "j2py.validation.ruff"
    if not validation.get("mypy_ok", True):
        return "j2py.validation.mypy"
    if not validation.get("ruff_ok", True):
        return "j2py.validation.ruff"
    return "j2py.validation"


def _validation_level(rule_id: str) -> str:
    return "error" if rule_id == "j2py.validation.syntax" else "warning"


def _validation_location(error: str, fallback_path: str) -> tuple[str, int | None]:
    path_match = _PATH_LINE_RE.match(error)
    if path_match is not None:
        return path_match.group("path"), int(path_match.group("line"))
    syntax_match = _SYNTAX_LINE_RE.search(error)
    if syntax_match is not None:
        return fallback_path, int(syntax_match.group("line"))
    return fallback_path, None


def _rule_descriptor(rule_id: str) -> dict[str, Any]:
    rule = RULES[rule_id]
    return {
        "id": rule_id,
        "name": rule["name"],
        "shortDescription": {"text": rule["shortDescription"]},
        "help": {"text": rule["help"]},
    }


def _result(
    rule_id: str,
    level: str,
    path: str,
    line: int | None,
    message: str,
) -> dict[str, Any]:
    physical_location: dict[str, Any] = {
        "artifactLocation": {"uri": path},
    }
    if line is not None and line > 0:
        physical_location["region"] = {"startLine": line}
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [{"physicalLocation": physical_location}],
    }
