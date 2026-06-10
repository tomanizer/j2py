"""Fixture tests for the rule-based skeleton translator."""

import ast
from pathlib import Path

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_file, parse_source
from j2py.translate.skeleton import translate_skeleton

FIXTURES = Path(__file__).parent.parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()


def _translate_source(source: str) -> tuple[str, float]:
    parsed = parse_source(source)
    return translate_skeleton(parsed, extract_symbols(parsed), CFG)


def _assert_valid_python(source: str) -> None:
    ast.parse(source)


def test_translate_hello_world_with_rule_layer_only() -> None:
    parsed = parse_file(FIXTURES / "java" / "HelloWorld.java")
    symbols = extract_symbols(parsed)

    python_source, coverage = translate_skeleton(parsed, symbols, CFG)

    assert python_source == (FIXTURES / "python" / "HelloWorld.py").read_text()
    assert coverage == 1.0
    _assert_valid_python(python_source)


def test_field_without_constructor_assignment_drops_coverage() -> None:
    python_source, coverage = _translate_source("public class FieldOnly { private int count; }")

    assert coverage < 1.0
    assert "TODO(j2py): field declaration not represented" in python_source
    _assert_valid_python(python_source)


def test_overloaded_methods_do_not_emit_duplicate_python_defs() -> None:
    python_source, coverage = _translate_source(
        """
        public class Over {
            public int get(int value) { return value; }
            public int get(String value) { return 1; }
        }
        """,
    )

    assert coverage < 1.0
    assert "TODO(j2py): overloaded method get requires LLM completion" in python_source
    assert "def get(" not in python_source
    _assert_valid_python(python_source)


def test_non_empty_collection_constructor_drops_coverage() -> None:
    python_source, coverage = _translate_source(
        """
        import java.util.ArrayList;
        import java.util.List;

        public class Copy {
            public List<String> copy(List<String> people) {
                List<String> copied = new ArrayList<>(people);
                return copied;
            }
        }
        """,
    )

    assert coverage < 1.0
    assert "__j2py_todo__('new ArrayList<>(people)')" in python_source
    _assert_valid_python(python_source)


def test_compound_assignment_drops_coverage() -> None:
    python_source, coverage = _translate_source(
        """
        public class Acc {
            private int count;

            public Acc(int count) {
                this.count = count;
            }

            public void inc(int delta) {
                count += delta;
            }
        }
        """,
    )

    assert coverage < 1.0
    assert "__j2py_todo__('count += delta')" in python_source
    assert "self.count = delta" not in python_source
    _assert_valid_python(python_source)
