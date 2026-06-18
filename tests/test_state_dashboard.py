from pathlib import Path

from j2py.llm.review import LlmReviewFinding
from j2py.pipeline import TranslationResult
from j2py.report import render_dashboard
from j2py.state import StateEntry, entry_from_result, load_state, save_state, state_path


def test_state_round_trip(tmp_path: Path) -> None:
    entry = StateEntry(
        source_path="src/Person.java",
        output_path="com/example/Person.py",
        sha256="abc123",
        translated_at="2026-06-13T12:00:00Z",
        confidence=0.87,
        used_llm=True,
        validation_ok=True,
        syntax_ok=True,
        mypy_ok=True,
        ruff_ok=True,
        todo_count=2,
        unhandled_count=1,
        loc=42,
    )

    save_state(tmp_path, {"src/Person.java": entry})

    assert state_path(tmp_path).exists()
    loaded = load_state(tmp_path)
    assert loaded["src/Person.java"] == entry


def test_dashboard_is_self_contained_sortable_html() -> None:
    html = render_dashboard(
        [
            StateEntry(
                source_path="src/Person.java",
                output_path="Person.py",
                sha256="abc",
                translated_at="2026-06-13T12:00:00Z",
                confidence=1.0,
                used_llm=False,
                validation_ok=True,
                syntax_ok=True,
                mypy_ok=True,
                ruff_ok=True,
                todo_count=0,
                unhandled_count=0,
                loc=10,
            ),
            StateEntry(
                source_path="src/ComplexBean.java",
                output_path="ComplexBean.py",
                sha256="def",
                translated_at="2026-06-13T12:01:00Z",
                confidence=0.45,
                used_llm=True,
                validation_ok=False,
                syntax_ok=True,
                mypy_ok=False,
                ruff_ok=True,
                todo_count=8,
                unhandled_count=3,
                loc=80,
                llm_review_ran=True,
                llm_review_count=2,
            ),
        ],
        title="Report",
    )

    assert "Average confidence" in html
    assert "Confidence Heatmap" in html
    assert "ComplexBean.java" in html
    assert "LLM-reviewed files" in html
    assert "LLM review findings" in html
    assert 'data-type="number"' in html
    assert "j2py-dashboard-data" in html
    assert "https://" not in html


def test_state_entry_tracks_llm_review_summary(tmp_path: Path) -> None:
    java = tmp_path / "Sample.java"
    java.write_text("class Sample {}\n")
    result = TranslationResult(
        source_path=java,
        python_source="class Sample:\n    pass\n",
        output_path=tmp_path / "Sample.py",
        llm_review_ran=True,
        llm_review_findings=[
            LlmReviewFinding(
                severity="warning",
                category="semantic",
                source_line=1,
                output_line=1,
                message="Verify behavior.",
            ),
        ],
    )

    entry = entry_from_result(result, source_root=tmp_path, output_root=tmp_path)

    assert entry.llm_review_ran is True
    assert entry.llm_review_count == 1
