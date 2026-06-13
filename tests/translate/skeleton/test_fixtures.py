"""Skeleton translator tests — graduated target fixtures."""


from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file, parse_source
from j2py.translate.skeleton import translate_skeleton, translate_skeleton_with_diagnostics
from tests.translate.skeleton.helpers import (
    CFG,
    FIXTURES,
    assert_valid_python,
)


@pytest.mark.parametrize(
    ("fixture_name", "expected_coverage"),
    [
        ("HelloWorld", 1.0),
        ("Fields", 1.0),
        ("AbstractClass", 1.0),
    ],
)
def test_translate_fixture_with_rule_layer(
    fixture_name: str,
    expected_coverage: float | None,
) -> None:
    parsed = parse_file(FIXTURES / "java" / f"{fixture_name}.java")
    symbols = extract_symbols(parsed)

    python_source, coverage = translate_skeleton(parsed, symbols, CFG)

    assert python_source == (FIXTURES / "python" / f"{fixture_name}.py").read_text()
    if expected_coverage is None:
        assert coverage < 1.0
    else:
        assert coverage == expected_coverage
    assert_valid_python(python_source)


def test_abstract_class_with_superclass_keeps_superclass_and_abc() -> None:
    parsed = parse_source(
        """
        class Base {
        }

        abstract class Specialized extends Base {
        }
        """
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert "from abc import ABC, abstractmethod" in result.source
    assert "class Base:" in result.source
    assert "class Specialized(Base, ABC):" in result.source
    assert_valid_python(result.source)


@pytest.mark.parametrize(
    ("fixture_name", "expected_fragments"),
    [
        (
            "ControlFlow",
            (
                "if value > 10:",
                "elif value == 10:",
                "else:",
                "for i in range(0, limit):",
                "total += i",
                "while total < 100:",
                "total += 1",
                "while True:",
                "total -= 1",
            ),
        ),
        (
            "Exceptions",
            (
                "try:",
                "except OSError as ex:",
                'raise RuntimeError("Failed to read") from ex',
                "finally:",
                "resource.close()",
            ),
        ),
    ],
)
def test_graduated_issue_2_target_fixtures_translate(
    fixture_name: str,
    expected_fragments: tuple[str, ...],
) -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / f"{fixture_name}.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    for fragment in expected_fragments:
        assert fragment in result.source
    assert_valid_python(result.source)





def test_graduated_issue_8_overloads_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "Overloads.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import overload" in result.source
    assert "@overload" in result.source
    assert 'def __init__(self, name: str = "default") -> None:' in result.source
    assert "self.name = name" in result.source
    assert "def add(self, left: str | int, right: str | int) -> str | int:" in result.source
    assert "return left + right" in result.source
    assert_valid_python(result.source)





def test_graduated_issue_44_overload_chains_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "OverloadChains.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import overload" in result.source
    # Chained this(...) delegation composes into one implementation signature.
    assert (
        'def __init__(self, default_target: str, feature_name_prefix: str = "", '
        "sequence_generator: dict[str, int] | None = None) -> None:"
    ) in result.source
    # The constructed default uses a None sentinel, never a mutable default value.
    assert "if sequence_generator is None:" in result.source
    assert "sequence_generator = {}" in result.source
    assert "dict[str, int] = {}" not in result.source
    # Builder-style forwarding overload becomes a default parameter.
    assert 'def generate(self, name: str, separator: str = "-") -> str:' in result.source
    assert "return self.feature_name_prefix + separator + name" in result.source
    assert_valid_python(result.source)





def test_graduated_issue_44_overload_dispatch_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "OverloadDispatch.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from j2py_runtime import overloaded" in result.source
    assert "NotImplementedError" not in result.source
    # Each Java overload stays a same-named def with its body translated 1:1.
    assert result.source.count("def register_type(") == 2
    assert (
        "def register_type(self, type_: TypeReference, type_hint: Consumer[Builder]) "
        "-> OverloadDispatch:"
    ) in result.source
    assert "*member_categories: MemberCategory" in result.source
    # Sibling overload calls re-enter the dispatcher through self.
    assert "return self.register_type(" in result.source
    # Constructor groups with arity collisions dispatch as well, with this(...)
    # delegation translated to self.__init__(...).
    assert result.source.count("def __init__(") == 3
    assert "self.__init__(name, generated_files, RuntimeHints())" in result.source
    # Redefinitions carry the systematic suppressions for mypy and ruff.
    assert result.source.count("# type: ignore[no-redef]  # noqa: F811") == 3
    assert_valid_python(result.source)





def test_graduated_issue_9_nested_types_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "NestedTypes.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from dataclasses import dataclass" in result.source
    assert "from enum import Enum" in result.source
    assert "from typing import Protocol" in result.source
    assert "class Writer(Protocol):" in result.source
    assert "class Labelled(Protocol):" in result.source
    assert "class Mode(Enum):" in result.source
    assert "# implements Labelled" in result.source
    assert 'FAST = ("fast", 1)' in result.source
    assert 'SAFE = ("safe", 2)' in result.source
    assert "display_name: str" in result.source
    assert "sort_order: int" in result.source
    assert "def __init__(self, display_name: str, sort_order: int) -> None:" in result.source
    assert "self.display_name = display_name" in result.source
    assert "self.sort_order = sort_order" in result.source
    assert "def label(self) -> str:" in result.source
    assert "return self.display_name" in result.source
    assert "def order(self) -> int:" in result.source
    assert "return self.sort_order" in result.source
    assert "@dataclass(frozen=True)" in result.source
    assert "class Entry:" in result.source
    assert "name: str" in result.source
    assert "order: int" in result.source
    assert "class Builder:" in result.source
    assert "def build(self, name: str) -> Entry:" in result.source
    assert "return Entry(name, 1)" in result.source
    assert "def anonymous_writer(self, prefix: str) -> Writer:" in result.source
    assert "class _J2pyAnonymous1(Writer):" in result.source
    assert "def write(self, value: str) -> None:" in result.source
    assert "print(prefix + value)" in result.source
    assert "return _J2pyAnonymous1()" in result.source
    assert "def local_entry(self, name: str) -> object:" in result.source
    assert "class LocalEntry:" in result.source
    assert "def value(self) -> str:" in result.source
    assert "return LocalEntry()" in result.source
    assert_valid_python(result.source)
    namespace: dict[str, object] = {}
    exec(result.source, namespace)
    mode = namespace["NestedTypes"].Mode
    assert mode.FAST.label() == "fast"
    assert mode.SAFE.order() == 2





def test_graduated_issue_20_functional_stream_target_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "Functional.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import Any" in result.source
    assert "def names(self, types: list[type[Any]]) -> list[str]:" in result.source
    # Accept "type_" (post-naming for builtin collision) or similar from current singularize;
    # the key is a working listcomp, no TODOs, and the method ref translated.
    comp = "return [" in result.source and "for " in result.source and " in types" in result.source
    assert comp
    assert "get_name()" in result.source
    assert "__j2py_todo__" not in result.source
    assert_valid_python(result.source)





def test_instanceof_pattern_variable_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "InstanceofExpression.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "if isinstance(value, str):" in result.source
    assert "text = value" in result.source
    assert "return text.strip()" in result.source
    assert_valid_python(result.source)





def test_cast_expression_target_fixture_translates_with_warning() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "CastExpression.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import cast" in result.source
    assert (
        "return cast(TypeReference, value).get_canonical_name()  # cast: (TypeReference)"
        in result.source
    )
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "Java reference cast translated to typing.cast; verify runtime type",
    ]
    assert_valid_python(result.source)





def test_bitwise_operator_target_fixtures_translate() -> None:
    bitwise = parse_file(FIXTURES / "java" / "targets" / "BitwiseOperators.java")
    bitwise_result = translate_skeleton_with_diagnostics(
        bitwise, extract_symbols(bitwise), CFG
    )

    assert bitwise_result.coverage == 1.0
    assert not bitwise_result.diagnostics.unhandled
    assert "return left & right | left ^ right" in bitwise_result.source
    assert "return value << 2 >> 1" in bitwise_result.source
    assert "return (value & 0xFFFFFFFF) >> (1 & 0x1F)" in bitwise_result.source
    assert "value = -1" in bitwise_result.source
    assert "return (value & 0xFFFFFFFFFFFFFFFF) >> (2 & 0x3F)" in bitwise_result.source
    assert "value = (value & 0xFFFFFFFF) >> (1 & 0x1F)" in bitwise_result.source
    assert "return (source.value() & 0xFFFFFFFF) >> (1 & 0x1F)" in bitwise_result.source
    assert [warning.reason for warning in bitwise_result.diagnostics.warnings] == [
        "unsigned right shift assumed 32-bit int width; verify operand type",
    ]
    assert "__j2py_todo__" not in bitwise_result.source
    assert_valid_python(bitwise_result.source)

    compound = parse_file(FIXTURES / "java" / "targets" / "CompoundAssignment.java")
    compound_result = translate_skeleton_with_diagnostics(
        compound, extract_symbols(compound), CFG
    )

    assert compound_result.coverage == 1.0
    assert not compound_result.diagnostics.unhandled
    assert "value &= mask" in compound_result.source
    assert "value |= flag" in compound_result.source
    assert "__j2py_todo__" not in compound_result.source
    assert_valid_python(compound_result.source)


def test_unsigned_right_shift_resolves_nested_field_java_type() -> None:
    parsed = parse_source(
        """
        class Outer {
            static class Holder { long bits; }
            long nested(Holder holder) { return holder.bits >>> 1; }
        }
        """,
        path=Path("Outer.java"),
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert "return (holder.bits & 0xFFFFFFFFFFFFFFFF) >> (1 & 0x3F)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_unsigned_right_shift_assign_evaluates_array_index_once() -> None:
    parsed = parse_source(
        """
        class Demo {
            int[] values;
            int index() { return 0; }
            void update() { values[index()] >>>= 1; }
        }
        """,
        path=Path("Demo.java"),
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert "_j2py_idx = self.index();" in result.source
    assert (
        "self.values[_j2py_idx] = (self.values[_j2py_idx] & 0xFFFFFFFF) >> (1 & 0x1F)"
        in result.source
    )
    assert "self.values[self.index()] = (self.values[self.index()]" not in result.source
    assert_valid_python(result.source)


def test_unsigned_right_shift_masks_shift_distance_for_int() -> None:
    parsed = parse_source(
        """
        class Demo {
            int shift(int value) { return value >>> 32; }
        }
        """,
        path=Path("Demo.java"),
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert "return (value & 0xFFFFFFFF) >> (32 & 0x1F)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_unsigned_right_shift_resolves_array_element_java_type() -> None:
    parsed = parse_source(
        """
        class Demo {
            long pick(long[] values, int i) { return values[i] >>> 1; }
        }
        """,
        path=Path("Demo.java"),
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert "return (values[i] & 0xFFFFFFFFFFFFFFFF) >> (1 & 0x3F)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)





def test_sized_array_creation_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "ArrayCreation.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "return [0] * size" in result.source
    assert "__j2py_todo__" not in result.source
    assert_valid_python(result.source)





def test_try_with_resources_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "TryWithResources.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "with factory.open() as resource:" in result.source
    assert "return resource.read()" in result.source
    assert "__j2py_todo__" not in result.source
    assert_valid_python(result.source)





def test_static_initializer_and_synchronized_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "StaticAndSynchronized.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "initialize()" in result.source
    assert "import threading" in result.source
    assert "self._j2py_lock = threading.Lock()" in result.source
    assert "with self._j2py_lock:" in result.source
    assert "with self:" not in result.source
    assert "run()" in result.source
    assert "__j2py_todo__" not in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)
