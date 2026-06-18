from pathlib import Path

from j2py.llm.review import LlmReviewFinding
from j2py.report import ReportInput, render_translation_report


def test_report_marks_todo_lines_with_expandable_diagnostics() -> None:
    html = render_translation_report(
        [
            ReportInput(
                source_path=Path("Sample.java"),
                java_source="class Sample {}",
                python_source="class Sample:\n    __j2py_todo__('missing')",
                confidence=0.5,
                used_llm=False,
                diagnostics=["line 2: unsupported construct", "line 7: other TODO"],
            )
        ],
        title="Review",
    )

    assert 'data-provenance="rule"' in html
    assert 'class="rule todo"' in html
    assert "<details><summary>TODO</summary>" in html
    assert "line 2: unsupported construct" in html
    assert "line 7: other TODO" in html
    todo_detail = html.split("<details><summary>TODO</summary>", 1)[1].split("</details>", 1)[0]
    assert "line 7: other TODO" not in todo_detail


def test_report_surfaces_llm_review_findings_separately() -> None:
    html = render_translation_report(
        [
            ReportInput(
                source_path=Path("Sample.java"),
                java_source="class Sample {}",
                python_source="class Sample:\n    pass",
                confidence=1.0,
                used_llm=False,
                diagnostics=[],
                llm_review_ran=True,
                llm_review_findings=[
                    LlmReviewFinding(
                        severity="warning",
                        category="semantics",
                        source_line=1,
                        output_line=2,
                        message="Check behavior.",
                        recommendation="Compare with Java tests.",
                    )
                ],
            )
        ],
        title="Review",
    )

    assert "LLM review findings" in html
    assert "Check behavior." in html
    assert "Compare with Java tests." in html
    assert "Java line 1" in html
    assert "Python line 2" in html
