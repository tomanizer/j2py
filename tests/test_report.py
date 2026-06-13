from pathlib import Path

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
