"""Release-candidate checklist documentation checks."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _release_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _release_dir() -> Path:
    return ROOT / "docs" / "releases" / _release_version()


CHECKLIST = _release_dir() / "CANDIDATE_EVIDENCE.md"


def test_release_candidate_checklist_is_linked_from_release_docs() -> None:
    readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    release_notes = (_release_dir() / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    checklist_path = f"releases/{_release_version()}/CANDIDATE_EVIDENCE.md"

    assert checklist_path in readme
    assert f"docs/{checklist_path}" in release_notes


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
