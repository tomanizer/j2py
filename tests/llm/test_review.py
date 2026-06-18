"""Tests for structured LLM review finding parsing."""

import json
from pathlib import Path

import pytest

from j2py.llm.prompts import build_review_prompt
from j2py.llm.review import LlmReviewFinding, parse_review_findings, review_findings_payload
from j2py.report import ReportInput, render_dashboard, render_translation_report
from j2py.state import StateEntry


def test_parse_review_findings_accepts_list_and_coerces_fields() -> None:
    findings = parse_review_findings(
        json.dumps(
            [
                {
                    "severity": "ERROR",
                    "category": "  semantic  ",
                    "source_line": "7",
                    "output_line": 3,
                    "message": "  Check behavior.  ",
                    "recommendation": "  Compare tests.  ",
                },
                {
                    "severity": "unknown",
                    "category": "",
                    "source_line": True,
                    "output_line": "not-a-number",
                    "message": "Fallback fields.",
                    "recommendation": 123,
                },
                {
                    "source_line": -1,
                    "output_line": [],
                    "message": "Default severity and category.",
                },
                {
                    "message": "No line references.",
                },
            ],
        ),
    )

    assert findings == [
        LlmReviewFinding(
            severity="error",
            category="semantic",
            source_line=7,
            output_line=3,
            message="Check behavior.",
            recommendation="Compare tests.",
        ),
        LlmReviewFinding(
            severity="warning",
            category="general",
            source_line=None,
            output_line=None,
            message="Fallback fields.",
        ),
        LlmReviewFinding(
            severity="warning",
            category="general",
            source_line=None,
            output_line=None,
            message="Default severity and category.",
        ),
        LlmReviewFinding(
            severity="warning",
            category="general",
            source_line=None,
            output_line=None,
            message="No line references.",
        ),
    ]
    assert review_findings_payload(findings)[0]["severity"] == "error"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"findings": {"not": "a-list"}}, "must contain a findings list"),
        ({"findings": ["bad-item"]}, "finding must be an object"),
        ({"findings": [{"message": "   "}]}, "finding is missing message"),
    ],
)
def test_parse_review_findings_rejects_invalid_payloads(
    payload: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_review_findings(json.dumps(payload))


def test_build_review_prompt_includes_optional_context_sections() -> None:
    _system, messages = build_review_prompt(
        java_source="class A {}",
        python_source="class A:\n    pass\n",
        context="package context",
        diagnostics="diagnostics",
        validation_summary="Validation passed.",
        structural_summary="Structural verification passed.",
        source_path="src/A.java",
        output_path="out/A.py",
    )

    prompt = messages[0]["content"]
    assert "<source_path>src/A.java</source_path>" in prompt
    assert "<output_path>out/A.py</output_path>" in prompt
    assert "<project_context>\npackage context\n</project_context>" in prompt
    assert "<rule_diagnostics>\ndiagnostics\n</rule_diagnostics>" in prompt
    assert "<validation_summary>\nValidation passed.\n</validation_summary>" in prompt
    assert "<structural_summary>\nStructural verification passed.\n</structural_summary>" in prompt

    _system, structural_only_messages = build_review_prompt(
        java_source="class B {}",
        python_source="class B:\n    pass\n",
        structural_summary="Structural verification skipped.",
    )

    structural_only_prompt = structural_only_messages[0]["content"]
    assert "<validation_summary>" not in structural_only_prompt
    assert (
        "<structural_summary>\nStructural verification skipped.\n</structural_summary>"
        in structural_only_prompt
    )


def test_report_renders_review_error_and_empty_findings() -> None:
    html = render_translation_report(
        [
            ReportInput(
                source_path=Path("Error.java"),
                java_source="class Error {}",
                python_source="class Error:\n    pass\n",
                confidence=1.0,
                used_llm=False,
                diagnostics=[],
                llm_review_ran=True,
                llm_review_error="provider unavailable",
            ),
            ReportInput(
                source_path=Path("Clean.java"),
                java_source="class Clean {}",
                python_source="class Clean:\n    pass\n",
                confidence=1.0,
                used_llm=False,
                diagnostics=[],
                llm_review_ran=True,
                llm_review_findings=[],
            ),
            ReportInput(
                source_path=Path("LineLess.java"),
                java_source="class LineLess {}",
                python_source="class LineLess:\n    pass\n",
                confidence=1.0,
                used_llm=False,
                diagnostics=[],
                llm_review_ran=True,
                llm_review_findings=[
                    LlmReviewFinding(
                        severity="info",
                        category="maintainability",
                        source_line=None,
                        output_line=None,
                        message="Check manually.",
                    ),
                ],
            ),
        ],
        title="Review",
    )

    assert "LLM review failed:" in html
    assert "provider unavailable" in html
    assert "LLM review:</strong> no findings." in html
    assert "Check manually." in html


def test_dashboard_renders_review_error_cell() -> None:
    html = render_dashboard(
        [
            StateEntry(
                source_path="Error.java",
                output_path="Error.py",
                sha256="abc",
                translated_at="2026-06-18T11:00:00Z",
                confidence=1.0,
                used_llm=False,
                validation_ok=True,
                syntax_ok=True,
                mypy_ok=True,
                ruff_ok=True,
                todo_count=0,
                unhandled_count=0,
                loc=1,
                llm_review_ran=True,
                llm_review_error="provider unavailable",
            ),
        ],
        title="Dashboard",
    )

    assert '<td data-value="0">error</td>' in html
