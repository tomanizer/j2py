"""Release-facing coverage inventory checks."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "RELEASE_TEST_COVERAGE_0.7.0.md"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _make_target_dependencies(target: str) -> set[str]:
    makefile = _read("Makefile")
    match = re.search(rf"^{re.escape(target)}:\s*([^#\n]*)", makefile, re.MULTILINE)
    assert match is not None, f"missing Makefile target: {target}"
    return set(match.group(1).split())


def test_release_coverage_inventory_is_linked_from_release_docs() -> None:
    readme = _read("docs/README.md")
    release_notes = _read("docs/RELEASE_NOTES_0.7.0.md")

    assert "RELEASE_TEST_COVERAGE_0.7.0.md" in readme
    assert "RELEASE_TEST_COVERAGE_0.7.0.md" in release_notes


def test_release_coverage_inventory_covers_headline_claims() -> None:
    text = INVENTORY.read_text(encoding="utf-8")

    required_evidence = [
        "tests/translate/skeleton/",
        "tests/equivalence/",
        "tests/test_doctor.py",
        "tests/test_sarif.py",
        "pyproject.toml` excludes `live_llm`",
        "tests/llm/test_e2e_llm.py` is explicitly marked `live_llm`",
        "tests/integration/test_petclinic_smoke.py",
        "tests/wire/test_fastapi_target.py",
        "tests/translate/test_jdbc_sqlalchemy_calls.py",
        "tests/translate/test_jdbc_row_mapper.py",
        "tests/translate/test_platform_imports.py::test_raw_jdbc_fixture_preserves_boundaries_without_java_imports",
        "tests/fixtures/java/RawJdbcBoundary.java",
        "tests/packaging/test_pyproject_dependencies.py",
        "make release-check",
    ]
    for evidence in required_evidence:
        assert evidence in text


def test_release_gate_keeps_live_llm_out_of_normal_release_validation() -> None:
    release_test_deps = _make_target_dependencies("release-test")
    release_check_deps = _make_target_dependencies("release-check")

    assert {
        "lock-check",
        "check",
        "test-targets",
        "test-behavior",
        "test-spring-smoke",
        "version-check",
        "import-smoke",
    } <= release_test_deps
    assert {"release-test", "dist-check"} <= release_check_deps

    assert "test-llm-e2e" not in release_test_deps
    assert "test-llm-gemini-e2e" not in release_test_deps
    assert 'pytest -m "not behavior and not live_llm' in _read("Makefile")
