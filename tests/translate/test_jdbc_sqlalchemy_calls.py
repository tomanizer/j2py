"""Spring JdbcTemplate lowering to SQLAlchemy Core scaffolding."""

from __future__ import annotations

import ast

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file, parse_source
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.translate.skeleton.helpers import CFG, FIXTURES


def test_jdbc_template_fixture_lowers_common_calls_to_sqlalchemy_core() -> None:
    parsed = parse_file(FIXTURES / "java" / "JdbcTemplateSqlAlchemyScaffold.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert "from sqlalchemy import text" in result.source
    assert "from typing import Any as JdbcTemplate" in result.source
    assert "from typing import Any as NamedParameterJdbcTemplate" in result.source
    assert "from org.springframework.jdbc" not in result.source
    assert (
        "self.jdbc_template_connection.execute("
        "text('update owners set first_name = :p1 where id = :p2'), "
        "{'p1': first_name, 'p2': id_}).rowcount"
    ) in result.source
    assert (
        "self.jdbc_template_connection.execute("
        "text('select name from owners where id = :p1'), "
        "{'p1': id_}).scalar_one()"
    ) in result.source
    assert (
        "self.named_jdbc_template_connection.execute("
        "text('update owners set first_name = :firstName where id = :id'), "
        "params).rowcount"
    ) in result.source
    assert (
        "self.named_jdbc_template_connection.execute("
        "text('select name from owners where id = :id'), params).scalar_one()"
    ) in result.source


def test_jdbc_template_row_mapper_callback_emits_explicit_todo() -> None:
    parsed = parse_file(FIXTURES / "java" / "JdbcTemplateSqlAlchemyScaffold.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert "from j2py_runtime import __j2py_todo__" in result.source
    assert (
        "__j2py_todo__('TODO(j2py): JdbcTemplate RowMapper/callback requires project row mapping')"
    ) in result.source
    assert any(
        diagnostic.category == "spring-jdbc-sqlalchemy-todo"
        and "RowMapper/callback" in diagnostic.reason
        for diagnostic in result.diagnostics.unhandled
    )


def test_jdbc_template_imports_sqlalchemy_only_when_call_is_lowered() -> None:
    parsed = parse_source(
        """
        import org.springframework.jdbc.core.JdbcTemplate;

        public class HoldsJdbcTemplate {
            private final JdbcTemplate jdbcTemplate;

            public HoldsJdbcTemplate(JdbcTemplate jdbcTemplate) {
                this.jdbcTemplate = jdbcTemplate;
            }

            public JdbcTemplate template() {
                return jdbcTemplate;
            }
        }
        """,
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert "from typing import Any as JdbcTemplate" in result.source
    assert "from sqlalchemy import text" not in result.source
    assert "def template(self) -> JdbcTemplate:" in result.source
