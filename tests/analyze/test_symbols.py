"""Tests for symbol extraction from parsed Java ASTs."""

from pathlib import Path

from j2py.parse.java_ast import parse_file
from j2py.analyze.symbols import extract_symbols

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
