"""Release-candidate checklist documentation checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "RELEASE_CANDIDATE_EVIDENCE_0.7.0.md"


def test_release_candidate_checklist_is_linked_from_release_docs() -> None:
    readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs" / "RELEASE_NOTES_0.7.0.md").read_text(
        encoding="utf-8",
    )

    assert "RELEASE_CANDIDATE_EVIDENCE_0.7.0.md" in readme
    assert "RELEASE_CANDIDATE_EVIDENCE_0.7.0.md" in release_notes


def test_release_candidate_checklist_records_clean_install_evidence() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")

    required = [
        "make release-check",
        "j2py_converter-0.7.0-py3-none-any.whl",
        "j2py_converter-0.7.0.tar.gz",
        "Clean core install smoke",
        "Clean Spring extra install smoke",
        "j2py --help",
        "j2py-wire --help",
        "missing-session-factory",
        "tests/packaging/test_pyproject_dependencies.py",
        "Create the GitHub release tag only after the final release PR is green and merged.",
    ]
    for item in required:
        assert item in text
