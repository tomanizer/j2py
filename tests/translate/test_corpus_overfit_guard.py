"""Guardrails against corpus fixture overfitting in the core rule layer."""

from __future__ import annotations
from __future__ import annotations

import re
from pathlib import Path

from tests.conftest import CORPUS_CONSTRUCT_FIXTURES, TARGET_FIXTURES

REPO_ROOT = Path(__file__).parents[2]
CORE_SOURCE_ROOTS = (
    REPO_ROOT / "j2py" / "translate",
    REPO_ROOT / "j2py" / "parse",
    REPO_ROOT / "j2py" / "analyze",
    REPO_ROOT / "j2py" / "validate",
)
CORE_SOURCE_FILES = (
    *(path for root in CORE_SOURCE_ROOTS for path in root.rglob("*.py")),
    REPO_ROOT / "j2py" / "pipeline.py",
)

# Generic fixture names that are also ordinary translator vocabulary.
GENERIC_FIXTURE_STEMS = {
    "Expressions",
}


def _fixture_stems() -> set[str]:
    fixture_paths = (
        *CORPUS_CONSTRUCT_FIXTURES.glob("*.java"),
        *TARGET_FIXTURES.glob("*.java"),
    )
    return {path.stem for path in fixture_paths} - GENERIC_FIXTURE_STEMS


def test_core_rule_layer_does_not_reference_corpus_fixture_stems() -> None:
    """Corpus examples should drive general rules, not fixture-name branches."""
    forbidden = _fixture_stems()
    assert forbidden, "No fixture stems were found. Ensure the fixture directories are populated."
    assert forbidden, "expected at least one corpus fixture stem to guard against"
    hits: list[str] = []

    for source_file in CORE_SOURCE_FILES:
        text = source_file.read_text(encoding="utf-8")
        for stem in sorted(forbidden):
            if re.search(rf"\b{re.escape(stem)}\b", text):
                hits.append(f"{source_file.relative_to(REPO_ROOT)} contains {stem!r}")

    assert not hits
