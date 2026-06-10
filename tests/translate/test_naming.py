"""Tests for camelCase → snake_case and reserved word handling."""

import pytest

from j2py.translate.rules.naming import camel_to_snake, safe_identifier, translate_method_name


@pytest.mark.parametrize("camel, snake", [
    ("myVariable", "my_variable"),
    ("getHTTPCode", "get_http_code"),
    ("XMLParser", "xml_parser"),
    ("getName", "get_name"),
    ("URL", "url"),
    ("setValueXML", "set_value_xml"),
    ("camelCase", "camel_case"),
])
def test_camel_to_snake(camel: str, snake: str):
    assert camel_to_snake(camel) == snake


@pytest.mark.parametrize("name, expected", [
    ("list", "list_"),
    ("type", "type_"),
    ("print", "print_"),
    ("myVar", "myVar"),
])
def test_safe_identifier(name: str, expected: str):
    assert safe_identifier(name) == expected
