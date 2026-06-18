"""Tests for SARIF export."""

from __future__ import annotations

import json
from pathlib import Path

from j2py.doctor import DoctorAssessment
from j2py.sarif import SARIF_VERSION, assessment_to_sarif, write_sarif


def test_assessment_to_sarif_maps_doctor_diagnostics() -> None:
    assessment = DoctorAssessment(
        payload={
            "schema_version": 1,
            "source": "src",
            "files": [
                {
                    "path": "Broken.java",
                    "parse_ok": False,
                    "parse_errors": [
                        {
                            "line": 3,
                            "node_type": "ERROR",
                            "reason": "Java parse error",
                            "text": "public void broken( }",
                        }
                    ],
                    "unresolved_imports": [
                        {
                            "import": "com.external.PaymentClient",
                            "category": "external-import",
                            "reason": "not covered by defaults",
                        }
                    ],
                    "translation": {
                        "semantic_warnings": [
                            {
                                "line": 5,
                                "node_type": "binary_expression",
                                "reason": "integer division may differ",
                                "text": "value / 2",
                            }
                        ],
                        "unhandled": [
                            {
                                "line": 7,
                                "node_type": "synchronized_statement",
                                "reason": "unsupported synchronization",
                                "text": "synchronized(lock)",
                            }
                        ],
                        "todos": ["TODO(j2py): manual port required"],
                        "validation": {
                            "ok": False,
                            "syntax_ok": True,
                            "ruff_ok": True,
                            "mypy_ok": False,
                            "errors": ['Broken.py:2: error: Name "PaymentClient" is not defined'],
                        },
                    },
                }
            ],
        }
    )

    payload = assessment_to_sarif(assessment).payload

    assert payload["version"] == SARIF_VERSION
    run = payload["runs"][0]
    rule_ids = {rule["id"] for rule in run["tool"]["driver"]["rules"]}
    result_rule_ids = {result["ruleId"] for result in run["results"]}
    assert {
        "j2py.parse-error",
        "j2py.semantic-warning",
        "j2py.unhandled-construct",
        "j2py.todo",
        "j2py.validation.mypy",
        "j2py.unresolved-import",
    } <= result_rule_ids
    assert result_rule_ids <= rule_ids
    parse_result = next(
        result for result in run["results"] if result["ruleId"] == "j2py.parse-error"
    )
    assert parse_result["level"] == "error"
    assert parse_result["locations"][0]["physicalLocation"]["region"]["startLine"] == 3
    mypy_result = next(
        result for result in run["results"] if result["ruleId"] == "j2py.validation.mypy"
    )
    assert mypy_result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == (
        "Broken.py"
    )
    assert mypy_result["locations"][0]["physicalLocation"]["region"]["startLine"] == 2


def test_sarif_output_is_deterministic(tmp_path: Path) -> None:
    assessment = DoctorAssessment(
        payload={
            "schema_version": 1,
            "source": "src",
            "files": [
                {
                    "path": "Sample.java",
                    "parse_ok": True,
                    "parse_errors": [],
                    "unresolved_imports": [],
                    "translation": {
                        "semantic_warnings": [],
                        "unhandled": [],
                        "todos": [],
                        "validation": None,
                    },
                }
            ],
        }
    )

    first = assessment_to_sarif(assessment)
    second = assessment_to_sarif(assessment)
    output = tmp_path / "j2py.sarif"
    write_sarif(output, first)

    assert first.to_json() == second.to_json()
    assert json.loads(output.read_text())["runs"][0]["results"] == []
