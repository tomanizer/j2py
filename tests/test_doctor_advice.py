"""Tests for doctor advice payload helpers."""

import json

from j2py.doctor import DoctorAssessment
from j2py.doctor_advice import (
    build_doctor_advice_context,
    render_doctor_advice_json,
)
from j2py.llm.prompts import ADVICE_PROMPT_VERSION


def _assessment_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "source": "src/main/java",
        "summary": {
            "files": 2,
            "classes": 1,
            "parse_failures": 1,
            "graph_warnings": 0,
            "semantic_warnings": 3,
            "unhandled_diagnostics": 4,
            "todo_lines": 0,
            "unresolved_imports": 2,
            "average_rule_coverage": 61.0,
            "average_risk_score": 14.5,
            "max_risk_score": 25.0,
            "min_risk_score": 5.0,
            "readiness_distribution": [],
            "top_risk_files": [
                {"path": "A.java", "risk_score": 10},
                {"path": "B.java", "risk_score": 20},
            ],
        },
        "files": [
            {
                "path": "A.java",
                "parse_ok": False,
                "risk_reasons": [
                    {"reason": "parse_error"},
                ],
                "rule_coverage": 0.1,
            },
            {"path": "B.java", "parse_ok": True},
        ],
        "unresolved_imports": [{"import": "com.external.Foo"}],
        "hotspots": {
            "unresolved_import_packages": [
                {"package": "com.external", "count": 2},
            ],
            "lowest_coverage_files": ["A.java"],
            "highest_risk_files": ["A.java", "B.java"],
            "unhandled_node_types": ["lambda_expression"],
            "semantic_warning_reasons": ["integer_division"],
        },
        "diagnostic_clusters": [
            {"owner": "parser", "occurrence_count": 3},
            {"owner": "type", "occurrence_count": 1},
            {"owner": "framework", "occurrence_count": 2},
        ],
        "config_suggestions": {
            "import_map": [{"java_import": "com.external.Foo", "python_import": "foo"}],
            "type_map": [{"java_type": "java.util.List", "python_type": "list"}],
            "annotation_map": [
                {"java_annotation": "Deprecated", "python_annotation": "TODO"},
            ],
        },
        "recommended_next_commands": ["j2py doctor diff before after"],
    }


def test_build_doctor_advice_context_clips_and_sorts() -> None:
    assessment = DoctorAssessment(payload=_assessment_payload())

    context, fingerprint, source = build_doctor_advice_context(assessment, max_evidence_items=1)

    assert source == "src/main/java"
    assert len(fingerprint) == 64
    parsed = json.loads(context)
    assert parsed["schema_version"] == 2
    assert parsed["summary"]["files"] == 2
    assert len(parsed["issue_slices"]["parse_failures"]) == 1
    assert len(parsed["issue_slices"]["top_risk_files"]) == 1
    assert len(parsed["issue_slices"]["rule_gap_signal_files"]) == 1
    assert len(parsed["issue_slices"]["top_warning_reasons"]) == 1


def test_render_doctor_advice_json_contains_envelope_fields() -> None:
    assessment = DoctorAssessment(payload=_assessment_payload())
    payload = render_doctor_advice_json(
        "# Migration plan",
        assessment=assessment,
        provider="anthropic",
        model="claude-test",
        output_format="json",
        max_evidence_items=1,
        evidence_fingerprint="abc",
    )

    data = json.loads(payload)
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-test"
    assert data["output_format"] == "json"
    assert data["prompt_version"] == ADVICE_PROMPT_VERSION
    assert data["input_fingerprint"] == "abc"
    assert data["advice_markdown"] == "# Migration plan"
    assert "generated_at" in data
