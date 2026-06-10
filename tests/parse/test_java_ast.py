"""Tests for the Java AST parser wrapper."""

from pathlib import Path

import pytest

from j2py.parse.java_ast import parse_source, parse_file

FIXTURES = Path(__file__).parent.parent / "fixtures" / "java"


def test_parse_hello_world():
    source = (FIXTURES / "HelloWorld.java").read_bytes()
    result = parse_source(source)
    assert not result.has_errors
    assert result.root.type == "program"


def test_find_class_declaration():
    source = b"public class Foo { }"
    result = parse_source(source)
    classes = list(result.root.find_all("class_declaration"))
    assert len(classes) == 1
    assert classes[0].child_by_field("name").text == "Foo"


def test_location_is_one_based():
    source = b"public class Foo { }"
    result = parse_source(source)
    classes = list(result.root.find_all("class_declaration"))
    assert classes[0].location.line == 1
