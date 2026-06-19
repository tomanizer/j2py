"""Release diagnostics and TODO wording audit checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "DIAGNOSTICS_TODO_AUDIT_0.7.0.md"


def test_diagnostics_todo_audit_is_linked_from_docs_index() -> None:
    readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert "DIAGNOSTICS_TODO_AUDIT_0.7.0.md" in readme


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
