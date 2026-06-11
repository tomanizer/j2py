"""Tests for structural verification of translated Python output."""

from pathlib import Path

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_source
from j2py.verify.structure import verify_structure


def _symbols(java_source: str):
    parsed = parse_source(java_source.encode(), path=Path("Example.java"))
    return extract_symbols(parsed)


def test_verify_structure_accepts_matching_class_and_method_order() -> None:
    symbols = _symbols(
        """
        public class Example {
            public Example() {}
            public int first() { return 1; }
            public int second() { return 2; }
        }
        """,
    )
    python_source = """\
class Example:
    def __init__(self) -> None:
        pass
    def first(self) -> int:
        return 1
    def second(self) -> int:
        return 2
"""

    result = verify_structure(symbols, python_source)

    assert result.ok


def test_verify_structure_reports_missing_method() -> None:
    symbols = _symbols(
        """
        public class Example {
            public int first() { return 1; }
            public int second() { return 2; }
        }
        """,
    )
    python_source = """\
class Example:
    def first(self) -> int:
        return 1
"""

    result = verify_structure(symbols, python_source)

    assert not result.ok
    assert result.errors == [
        "Missing method in class Example: second",
        "Method order changed in class Example: expected ['first', 'second'], got ['first']",
    ]


def test_verify_structure_reports_method_order_change() -> None:
    symbols = _symbols(
        """
        public class Example {
            public int first() { return 1; }
            public int second() { return 2; }
        }
        """,
    )
    python_source = """\
class Example:
    def second(self) -> int:
        return 2
    def first(self) -> int:
        return 1
"""

    result = verify_structure(symbols, python_source)

    assert not result.ok
    assert result.errors == [
        "Method order changed in class Example: expected ['first', 'second'], "
        "got ['second', 'first']",
    ]
