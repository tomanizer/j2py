"""Tests for the Java AST parser wrapper."""

from pathlib import Path

from j2py.parse.java_ast import parse_source

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


def test_malformed_source_sets_has_errors() -> None:
    result = parse_source(b"public class Broken { void foo( { }")

    assert result.has_errors
    assert result.errors


def test_nullable_varargs_type_use_annotation_is_parser_error() -> None:
    """Guava Platform.java: tree-sitter-java ERROR on Jspecify varargs annotations (#160)."""
    result = parse_source(
        b"""class Platform {
  static String lenientFormat(String template, @Nullable Object @Nullable ... args) {
    return template;
  }
}""",
    )

    assert result.has_errors
    assert any(error.type == "ERROR" for error in result.errors)
    assert any("... args" in error.text for error in result.errors)
