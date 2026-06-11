"""Tests for symbol extraction from parsed Java ASTs."""

from pathlib import Path

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file, parse_source

FIXTURES = Path(__file__).parent.parent / "fixtures" / "java"


def test_extract_hello_world_symbols():
    parsed = parse_file(FIXTURES / "HelloWorld.java")
    symbols = extract_symbols(parsed)

    assert symbols.package == "com.example"
    assert len(symbols.classes) == 1

    cls = symbols.classes[0]
    assert cls.name == "HelloWorld"
    assert not cls.is_interface
    assert not cls.is_enum

    method_names = {m.name for m in cls.methods}
    assert "getName" in method_names
    assert "setName" in method_names
    assert "greetAll" in method_names
    assert "main" in method_names

    field_names = {f.name for f in cls.fields}
    assert "name" in field_names
    assert "count" in field_names


def test_nested_declarations_are_inner_class_symbols() -> None:
    parsed = parse_source(
        """
        package com.example;

        public class Outer {
            private String name;

            public static class Inner {
                public String value() { return "x"; }
            }

            public interface Named {
                String name();
            }
        }
        """,
    )

    symbols = extract_symbols(parsed)

    assert [cls.name for cls in symbols.classes] == ["Outer"]
    outer = symbols.classes[0]
    assert [inner.name for inner in outer.inner_classes] == ["Inner", "Named"]
    assert outer.fields[0].name == "name"
    assert outer.inner_classes[0].methods[0].name == "value"


def test_record_declarations_are_extracted_as_class_symbols() -> None:
    parsed = parse_source(
        """
        package com.example;

        public record Point(int x, int y) {
            public int magnitude() {
                return x + y;
            }
        }
        """,
    )

    symbols = extract_symbols(parsed)

    assert [cls.name for cls in symbols.classes] == ["Point"]
    point = symbols.classes[0]
    assert point.is_record
    assert not point.is_interface
    assert not point.is_enum
    assert [field.name for field in point.fields] == ["x", "y"]
    assert [field.java_type for field in point.fields] == ["int", "int"]
    assert [method.name for method in point.methods] == ["magnitude"]


def test_inner_record_is_nested_class_symbol() -> None:
    parsed = parse_file(FIXTURES / "targets" / "NestedTypes.java")
    symbols = extract_symbols(parsed)

    outer = symbols.classes[0]
    entry = next(inner for inner in outer.inner_classes if inner.name == "Entry")
    assert entry.is_record
    assert [field.name for field in entry.fields] == ["name", "order"]
