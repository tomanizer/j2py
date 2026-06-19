"""Release performance baseline documentation checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "PERFORMANCE_BASELINE_0.7.0.md"


def test_performance_baseline_is_linked_from_release_docs() -> None:
    readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs" / "RELEASE_NOTES_0.7.0.md").read_text(
        encoding="utf-8",
    )

    assert "PERFORMANCE_BASELINE_0.7.0.md" in readme
    assert "PERFORMANCE_BASELINE_0.7.0.md" in release_notes


def test_performance_baseline_records_required_issue_585_paths() -> None:
    text = BASELINE.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    required = [
        "Small parse only",
        "Medium package translate, no validation",
        "Spring fixture CLI translate + wire + validate",
        "Corpus reporting slice",
        "tests/fixtures/java/HelloWorld.java",
        "tests/fixtures/case_study/commons_lang_tuple/java",
        "tests/fixtures/java/SpringJdbcConfiguration.java",
        "scripts/corpus/translate_corpus.py",
        "make corpus-hotspots",
        "validation subprocess startup",
        "No code optimization was merged in this slice.",
    ]
    for item in required:
        assert item in normalized
