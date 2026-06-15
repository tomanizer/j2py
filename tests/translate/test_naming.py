"""Tests for camelCase → snake_case and reserved word handling."""

import pytest

from j2py.translate.rules.naming import camel_to_snake, safe_attribute_name, safe_identifier


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
