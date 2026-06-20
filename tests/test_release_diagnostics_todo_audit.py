"""Release diagnostics and TODO wording audit checks."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
RELEASE_VERSION = str(_PYPROJECT["project"]["version"])
RELEASE_DIR = ROOT / "docs" / "releases" / RELEASE_VERSION
AUDIT = RELEASE_DIR / "DIAGNOSTICS_TODO_AUDIT.md"


def test_diagnostics_todo_audit_is_linked_from_docs_index() -> None:
    readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert f"releases/{RELEASE_VERSION}/DIAGNOSTICS_TODO_AUDIT.md" in readme


def test_diagnostics_todo_audit_records_release_boundary_messages() -> None:
    text = AUDIT.read_text(encoding="utf-8")

    required = [
        "jdbc-boundary",
        "spring-jdbc-sqlalchemy-todo",
        "spring-jdbc-boundary",
        "import_map/type_map",
        "manual mapper port",
        "SQLAlchemy Engine, Connection, or Session",
        "manually port JPQL query",
        "manually port Spring Data derived query method",
        "Java parse errors detected; skipping LLM completion",
    ]
    for item in required:
        assert item in text
