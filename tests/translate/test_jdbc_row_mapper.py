"""Spring RowMapper lowering to SQLAlchemy row mappings."""

from __future__ import annotations

import ast

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.translate.skeleton.helpers import CFG, FIXTURES


def _row_mapper_result():
    parsed = parse_file(FIXTURES / "java" / "JdbcRowMapperScaffold.java")
    return translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)


def test_lambda_row_mapper_query_lowers_to_sqlalchemy_mappings_list() -> None:
    result = _row_mapper_result()

    ast.parse(result.source)
    assert "from sqlalchemy import text" in result.source
    assert (
        "return [Owner(row['id'], row['first_name'], row['last_name']) "
        "for row in self.jdbc_template_connection.execute("
        "text('select id, first_name, last_name from owners')).mappings()]"
    ) in result.source
    assert any(
        diagnostic.category == "spring-jdbc-row-mapper"
        and diagnostic.facts.get("mapper_kind") == "lambda"
        for diagnostic in result.diagnostics.handled
    )


def test_lambda_row_mapper_query_for_object_lowers_to_single_row_mapping() -> None:
    result = _row_mapper_result()

    ast.parse(result.source)
    assert (
        "return (lambda row: Owner(row['id'], row['first_name'], row['last_name']))("
        "self.jdbc_template_connection.execute("
        "text('select id, first_name, last_name from owners where id = :p1'), "
        "{'p1': id_}).mappings().one())"
    ) in result.source


def test_anonymous_row_mapper_with_simple_return_lowers_deterministically() -> None:
    result = _row_mapper_result()

    ast.parse(result.source)
    assert "def anonymous_owner(self, id_: int) -> Owner:" in result.source
    assert "_J2pyAnonymous" not in result.source
    assert (
        "self.jdbc_template_connection.execute("
        "text('select id, first_name, last_name from owners where id = :p1'), "
        "{'p1': id_}).mappings().one())"
    ) in result.source
    assert any(
        diagnostic.category == "spring-jdbc-row-mapper"
        and diagnostic.facts.get("mapper_kind") == "anonymous"
        and diagnostic.facts.get("target_type") == "Owner"
        for diagnostic in result.diagnostics.handled
    )


def test_bean_property_row_mapper_lowers_to_model_kwargs_scaffold() -> None:
    result = _row_mapper_result()

    ast.parse(result.source)
    assert (
        "return [Owner(**dict(row)) for row in "
        "self.jdbc_template_connection.execute("
        "text('select id, first_name, last_name from owners')).mappings()]"
    ) in result.source
    assert (
        "return (lambda row: Owner(**dict(row)))("
        "self.named_jdbc_template_connection.execute("
        "text('select id, first_name, last_name from owners where id = :id'), "
        "params).mappings().one())"
    ) in result.source


def test_unsupported_row_mapper_method_reference_remains_explicit_todo() -> None:
    result = _row_mapper_result()

    ast.parse(result.source)
    assert "from j2py_runtime import __j2py_todo__" in result.source
    assert (
        "__j2py_todo__('TODO(j2py): JdbcTemplate RowMapper/callback requires manual "
        "mapper port; lower to SQLAlchemy row mapping or a project DB facade')"
    ) in result.source
    assert any(
        diagnostic.category == "spring-jdbc-sqlalchemy-todo"
        and "manual mapper port" in diagnostic.reason
        for diagnostic in result.diagnostics.unhandled
    )
