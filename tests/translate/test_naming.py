"""Tests for camelCase → snake_case and reserved word handling."""

import pytest

from j2py.translate.rules.naming import (
    camel_to_snake,
    safe_attribute_name,
    safe_identifier,
    translate_field_name,
)


@pytest.mark.parametrize(
    "camel, snake",
    [
        ("myVariable", "my_variable"),
        ("getHTTPCode", "get_http_code"),
        ("XMLParser", "xml_parser"),
        ("getName", "get_name"),
        ("URL", "url"),
        ("setValueXML", "set_value_xml"),
        ("camelCase", "camel_case"),
    ],
)
def test_camel_to_snake(camel: str, snake: str):
    assert camel_to_snake(camel) == snake


@pytest.mark.parametrize(
    "name, expected",
    [
        ("list", "list_"),
        ("type", "type_"),
        ("print", "print_"),
        ("myVar", "myVar"),
    ],
)
def test_safe_identifier(name: str, expected: str):
    assert safe_identifier(name) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("open", "open"),
        ("list", "list"),
        ("class", "class_"),
        ("myVar", "myVar"),
    ],
)
def test_safe_attribute_name(name: str, expected: str):
    assert safe_attribute_name(name) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("LF", "LF"),  # Java CONSTANT_CASE — must not be lowercased
        ("CR", "CR"),
        ("NUL", "NUL"),
        ("MAX_VALUE", "MAX_VALUE"),
        ("MIN_VALUE", "MIN_VALUE"),
        ("EMPTY_STRING", "EMPTY_STRING"),
    ],
)
def test_translate_field_name_preserves_constant_case(name: str, expected: str):
    assert translate_field_name(name) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("myField", "my_field"),
        ("someValue", "some_value"),
        ("MyField", "my_field"),  # PascalCase → snake_case (has lowercase letters)
        ("getHTTPCode", "get_http_code"),
    ],
)
def test_translate_field_name_snake_cases_camel(name: str, expected: str):
    assert translate_field_name(name) == expected
