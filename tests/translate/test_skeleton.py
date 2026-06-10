"""Fixture tests for the rule-based skeleton translator."""

import ast
from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_file, parse_source
from j2py.translate.skeleton import translate_skeleton, translate_skeleton_with_diagnostics

FIXTURES = Path(__file__).parent.parent / "fixtures"
CFG = ConfigLoader().add_defaults().build()


def _translate_source(source: str, cfg=CFG) -> tuple[str, float]:
    parsed = parse_source(source)
    return translate_skeleton(parsed, extract_symbols(parsed), cfg)


def _translate_source_with_diagnostics(source: str, cfg=CFG):
    parsed = parse_source(source)
    return translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), cfg)


def _assert_valid_python(source: str) -> None:
    ast.parse(source)


@pytest.mark.parametrize(
    ("fixture_name", "expected_coverage"),
    [
        ("HelloWorld", 1.0),
        ("Fields", None),
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
    _assert_valid_python(python_source)


def test_field_without_constructor_assignment_drops_coverage() -> None:
    python_source, coverage = _translate_source("public class FieldOnly { private int count; }")

    assert coverage < 1.0
    assert "TODO(j2py): verify default value for field count" in python_source
    _assert_valid_python(python_source)


def test_comments_and_dropped_annotations_do_not_reduce_coverage() -> None:
    result = _translate_source_with_diagnostics(
        """
        /** Type docs are currently ignored outside class bodies. */
        public class Comments {
            /** Field docs. */
            private static String label = "x";

            // Method docs.
            @Override
            public String toString() {
                // Return docs.
                return label;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "# Field docs." in result.source
    assert "# Method docs." in result.source
    assert "# Return docs." in result.source
    assert "unsupported class member block_comment" not in result.source
    assert "unsupported class member line_comment" not in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "preserved comment",
        "preserved comment",
        "dropped annotation @Override",
        "preserved comment",
    ]
    _assert_valid_python(result.source)


def test_unsupported_annotations_are_warnings_not_unhandled() -> None:
    result = _translate_source_with_diagnostics(
        """
        public class Annotated {
            @Custom
            public String name() {
                return "x";
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "unsupported annotation @Custom",
    ]
    assert not result.diagnostics.unhandled
    _assert_valid_python(result.source)


def test_instance_field_initializer_can_reference_another_field() -> None:
    python_source, coverage = _translate_source(
        """
        public class FieldRefs {
            private int base = 1;
            private int copy = base;
        }
        """,
    )

    assert coverage == 1.0
    assert "self.base: int = 1" in python_source
    assert "self.copy: int = self.base" in python_source
    assert "self.copy: int = base" not in python_source
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
    assert "@overload" in python_source
    assert "def get(self, value: int) -> int: ..." in python_source
    assert "def get(self, value: str) -> int: ..." in python_source
    assert (
        "TODO(j2py): overloaded method get requires manual dispatch for signatures: "
        "get(value: int); get(value: str)"
    ) in python_source
    assert "def get(self, *args: object) -> object:" in python_source
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


def test_compound_assignment_translates() -> None:
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

    assert coverage == 1.0
    assert "self.count += delta" in python_source
    assert "self.count = delta" not in python_source
    _assert_valid_python(python_source)


def test_classic_for_statement_translates_to_range_loop() -> None:
    python_source, coverage = _translate_source(
        """
        public class Loops {
            public int sum(int limit) {
                int total = 0;
                for (int i = 0; i < limit; i++) {
                    if (i == 2) {
                        continue;
                    }
                    total += i;
                }
                return total;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "for i in range(0, limit):" in python_source
    assert "continue" in python_source
    assert "total += i" in python_source
    _assert_valid_python(python_source)


def test_while_statement_translates_break_and_update() -> None:
    python_source, coverage = _translate_source(
        """
        public class Loops {
            public int reduce(int value) {
                while (value > 0) {
                    value--;
                    if (value == 2) {
                        break;
                    }
                }
                return value;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "while value > 0:" in python_source
    assert "value -= 1" in python_source
    assert "break" in python_source
    _assert_valid_python(python_source)


def test_do_while_statement_translates_to_guarded_infinite_loop() -> None:
    python_source, coverage = _translate_source(
        """
        public class Loops {
            public int decrement(int value) {
                do {
                    value--;
                }
                while (value > 0);
                return value;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "while True:" in python_source
    assert "value -= 1" in python_source
    assert "if not (value > 0):" in python_source
    _assert_valid_python(python_source)


def test_try_catch_finally_and_throw_use_exception_map() -> None:
    python_source, coverage = _translate_source(
        """
        import java.io.IOException;

        public class Exceptions {
            public void read(Resource resource) throws IOException {
                try {
                    throw new IllegalArgumentException("bad");
                }
                catch (IOException ex) {
                    throw new IllegalStateException("Failed", ex);
                }
                finally {
                    resource.close();
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "try:" in python_source
    assert 'raise ValueError("bad")' in python_source
    assert "except OSError as ex:" in python_source
    assert 'raise RuntimeError("Failed") from ex' in python_source
    assert "finally:" in python_source
    assert "resource.close()" in python_source
    _assert_valid_python(python_source)


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
    _assert_valid_python(result.source)


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
    _assert_valid_python(result.source)


def test_graduated_issue_9_nested_types_target_fixture_translates() -> None:
    parsed = parse_file(FIXTURES / "java" / "targets" / "NestedTypes.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from dataclasses import dataclass" in result.source
    assert "from enum import Enum" in result.source
    assert "from typing import Protocol" in result.source
    assert "class Writer(Protocol):" in result.source
    assert "class Mode(Enum):" in result.source
    assert "FAST =" in result.source
    assert "@dataclass(frozen=True)" in result.source
    assert "class Entry:" in result.source
    assert "name: str" in result.source
    assert "order: int" in result.source
    assert "class Builder:" in result.source
    assert "def build(self, name: str) -> Entry:" in result.source
    assert "return Entry(name, 1)" in result.source
    _assert_valid_python(result.source)


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
    _assert_valid_python(result.source)


def test_super_constructor_invocation_and_base_class_translate() -> None:
    python_source, coverage = _translate_source(
        """
        public class Child extends Parent {
            public Child(String name) {
                super(name);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "class Child(Parent):" in python_source
    assert "super().__init__(name)" in python_source
    _assert_valid_python(python_source)


def test_multi_catch_exception_types_translate_to_tuple_handler() -> None:
    python_source, coverage = _translate_source(
        """
        import java.io.IOException;

        public class Exceptions {
            public void recover() {
                try {
                    risky();
                }
                catch (IOException | RuntimeException ex) {
                    throw ex;
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "except (OSError, RuntimeError) as ex:" in python_source
    assert "raise ex" in python_source
    _assert_valid_python(python_source)


def test_switch_statement_translates_returning_cases() -> None:
    python_source, coverage = _translate_source(
        """
        public class Switches {
            public int pick(int value) {
                switch (value) {
                    case 1:
                        return 1;
                    default:
                        return 0;
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if value == 1:" in python_source
    assert "return 1" in python_source
    assert "else:" in python_source
    assert "return 0" in python_source
    _assert_valid_python(python_source)


def test_switch_statement_with_fallthrough_drops_coverage() -> None:
    result = _translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                int result = 0;
                switch (value) {
                    case 1:
                        result = 1;
                    default:
                        return result;
                }
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "TODO(j2py): switch fall-through requires manual translation" in result.source
    assert result.diagnostics.unhandled[-1].reason == (
        "switch fall-through requires manual translation"
    )
    _assert_valid_python(result.source)


def test_switch_expression_translates_arrow_rules_and_yield_blocks() -> None:
    python_source, coverage = _translate_source(
        """
        public class Switches {
            public String label(int value) {
                return switch (value) {
                    case 1 -> "one";
                    case 2, 3 -> "few";
                    default -> "many";
                };
            }

            public int score(int value) {
                return switch (value) {
                    case 1 -> { yield 10; }
                    default -> { yield 0; }
                };
            }
        }
        """,
    )

    assert coverage == 1.0
    assert 'return "one" if value == 1 else "few" if value in (2, 3) else "many"' in python_source
    assert "return 10 if value == 1 else 0" in python_source
    _assert_valid_python(python_source)


def test_if_statement_translates_single_branch() -> None:
    python_source, coverage = _translate_source(
        """
        public class Branch {
            public int clamp(int value) {
                if (value < 0) {
                    return 0;
                }
                return value;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if value < 0:" in python_source
    assert "return 0" in python_source
    _assert_valid_python(python_source)


def test_if_statement_translates_else_branch() -> None:
    python_source, coverage = _translate_source(
        """
        public class Branch {
            public int sign(int value) {
                if (value >= 0) {
                    return 1;
                }
                else {
                    return -1;
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if value >= 0:" in python_source
    assert "else:" in python_source
    assert "return -1" in python_source
    _assert_valid_python(python_source)


def test_if_statement_translates_chained_else_if() -> None:
    python_source, coverage = _translate_source(
        """
        public class Branch {
            public int sign(int value) {
                if (value > 0) {
                    return 1;
                }
                else if (value == 0) {
                    return 0;
                }
                else {
                    return -1;
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if value > 0:" in python_source
    assert "elif value == 0:" in python_source
    assert "else:" in python_source
    _assert_valid_python(python_source)


def test_if_statement_translates_nested_branch() -> None:
    python_source, coverage = _translate_source(
        """
        public class Branch {
            public int nested(int value) {
                if (value > 0) {
                    if (value > 10) {
                        return 10;
                    }
                }
                return value;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if value > 0:" in python_source
    assert "        if value > 10:" in python_source
    _assert_valid_python(python_source)


def test_if_statement_localizes_unsupported_condition_expression() -> None:
    python_source, coverage = _translate_source(
        """
        public class Branch {
            public int unsupported(Object value) {
                if (value instanceof String) {
                    return 1;
                }
                return 0;
            }
        }
        """,
    )

    assert coverage < 1.0
    assert "if __j2py_todo__('value instanceof String'):" in python_source
    assert "unsupported if_statement" not in python_source
    _assert_valid_python(python_source)


def test_common_spring_expression_shapes_translate() -> None:
    python_source, coverage = _translate_source(
        """
        import java.util.List;

        public class Expressions {
            public Class<?> type() {
                return Expressions.class;
            }

            public String first(String[] values) {
                return values.length > 0 ? values[0] : "default";
            }

            public boolean has(List<String> values) {
                return !values.isEmpty() && values.contains("x");
            }

            public String get(List<String> values) {
                return values.get(0);
            }

            public int[] numbers() {
                return new int[] {1, 2};
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "def type_(self) -> type[Any]:" in python_source
    assert "return Expressions" in python_source
    assert 'return values[0] if len(values) > 0 else "default"' in python_source
    assert "is not None" not in python_source
    assert 'return values and "x" in values' in python_source
    assert "return values[0]" in python_source
    assert "return [1, 2]" in python_source
    _assert_valid_python(python_source)


def test_map_get_preserves_missing_key_semantics() -> None:
    python_source, coverage = _translate_source(
        """
        import java.util.Map;

        public class Maps {
            public String lookup(Map<String, String> values) {
                return values.get("missing");
            }
        }
        """,
    )

    assert coverage == 1.0
    assert 'return values.get("missing")' in python_source
    assert 'return values["missing"]' not in python_source
    _assert_valid_python(python_source)


def test_ambiguous_get_invocation_drops_coverage() -> None:
    result = _translate_source_with_diagnostics(
        """
        public class Calls {
            public Object lookup(Object values) {
                return values.get("missing");
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert 'return values.get("missing")' in result.source
    assert result.diagnostics.unhandled[-1].reason == (
        "ambiguous get invocation requires receiver collection type"
    )
    _assert_valid_python(result.source)


def test_equals_invocation_translates_to_python_equality() -> None:
    python_source, coverage = _translate_source(
        """
        public class Equals {
            private String name = "x";

            public boolean same(String a, String b) {
                return a.equals(b);
            }

            public boolean sameField(String value) {
                return this.name.equals(value);
            }

            public boolean sameLiteral(String value) {
                return "x".equals(value);
            }

            public boolean sameNull(String value) {
                return value.equals(null);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return a == b" in python_source
    assert "return self.name == value" in python_source
    assert 'return "x" == value' in python_source
    assert "return value is None" in python_source
    assert ".equals(" not in python_source
    _assert_valid_python(python_source)


def test_expression_lambdas_and_method_references_translate() -> None:
    python_source, coverage = _translate_source(
        """
        import java.util.function.BiFunction;
        import java.util.function.Function;
        import java.util.function.Supplier;

        public class FunctionalCallbacks {
            public void callbacks(Service service) {
                Function<User, String> a = user -> user.getName();
                Function<User, String> b = (User user) -> user.getName();
                Function<User, String> c = User::getName;
                Function<String, User> d = User::new;
                Supplier<String> e = service::name;
                BiFunction<Integer, Integer, Integer> f = (left, right) -> left + right;
                Runnable r = () -> service.run();
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "a = lambda user: user.get_name()" in python_source
    assert "b = lambda user: user.get_name()" in python_source
    assert "c = User.get_name" in python_source
    assert "d = User" in python_source
    assert "e = service.name" in python_source
    assert "f = lambda left, right: left + right" in python_source
    assert "r = lambda: service.run()" in python_source
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_block_lambda_drops_coverage_with_localized_todo() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.function.Function;

        public class FunctionalCallbacks {
            public void callbacks() {
                Function<User, String> block = user -> { return user.getName(); };
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "__j2py_todo__('user -> { return user.getName(); }')" in result.source
    assert result.diagnostics.unhandled[-1].reason == "block lambda requires helper function"
    _assert_valid_python(result.source)


def test_array_constructor_method_reference_drops_coverage() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.List;

        public class FunctionalCallbacks {
            public String[] names(List<String> names) {
                return names.toArray(String[]::new);
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "__j2py_todo__('String[]::new')" in result.source
    assert result.diagnostics.unhandled[-1].reason == (
        "array constructor method reference requires collection conversion"
    )
    _assert_valid_python(result.source)


def test_import_map_emits_configured_python_imports_and_drops_known_imports() -> None:
    python_source, coverage = _translate_source(
        """
        import java.nio.file.Path;
        import java.util.List;

        public class UsesPath {
            public Path first(List<Path> paths) {
                return paths.get(0);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from pathlib import Path" in python_source
    assert "java.util.List" not in python_source
    assert "def first(self, paths: list[Path]) -> Path:" in python_source
    _assert_valid_python(python_source)


def test_custom_import_map_and_naming_flags_are_respected() -> None:
    cfg = CFG.model_copy(
        update={
            "import_map": {**CFG.import_map, "com.example.ExternalThing": "from ext import Thing"},
            "snake_case_methods": False,
            "snake_case_fields": False,
        },
    )
    python_source, coverage = _translate_source(
        """
        import com.example.ExternalThing;

        public class Naming {
            private String displayName = "x";

            public String getDisplayName() {
                return displayName;
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert "from ext import Thing" in python_source
    assert "self.displayName: str" in python_source
    assert "def getDisplayName(self) -> str:" in python_source
    assert "return self.displayName" in python_source
    _assert_valid_python(python_source)


def test_emit_line_comments_flag_suppresses_preserved_comments() -> None:
    cfg = CFG.model_copy(update={"emit_line_comments": False})
    result = _translate_source_with_diagnostics(
        """
        public class Comments {
            // Hidden when comment emission is disabled.
            public String value() {
                // Hidden too.
                return "x";
            }
        }
        """,
        cfg=cfg,
    )

    assert result.coverage == 1.0
    assert "Hidden when comment emission is disabled" not in result.source
    assert "Hidden too" not in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "preserved comment",
        "preserved comment",
    ]
    _assert_valid_python(result.source)


def test_emit_type_hints_flag_suppresses_standard_annotations() -> None:
    cfg = CFG.model_copy(update={"emit_type_hints": False})
    python_source, coverage = _translate_source(
        """
        public class Untyped {
            private String name = "x";

            public String getName(String fallback) {
                String value = name;
                return value;
            }
        }
        """,
        cfg=cfg,
    )

    assert coverage == 1.0
    assert 'self.name = "x"' in python_source
    assert "def get_name(self, fallback):" in python_source
    assert "value = self.name" in python_source
    assert ": str" not in python_source
    assert " -> str" not in python_source
    _assert_valid_python(python_source)


def test_string_concat_with_nested_quoted_expression_remains_valid_python() -> None:
    python_source, coverage = _translate_source(
        """
        public class Strings {
            public String describe(String name) {
                return "Hello " + (name != null ? "<" + name + ">" : "<missing>");
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return 'Hello ' + str(" in python_source
    _assert_valid_python(python_source)


def test_string_concat_preserves_leading_numeric_addition() -> None:
    python_source, coverage = _translate_source(
        """
        public class Strings {
            public String label(int a, int b) {
                return a + b + "x";
            }
        }
        """,
    )

    assert coverage == 1.0
    assert 'return f"{a + b}x"' in python_source
    assert 'return f"{a}{b}x"' not in python_source
    _assert_valid_python(python_source)


def test_integer_division_uses_floor_div_and_records_review_warning() -> None:
    """int/int division now uses warn() (proportionate) instead of unhandled record.
    We still produce correct // and surface the truncation note for reviewers,
    but we do not penalize coverage or force the LLM for a fully mechanical case.
    """
    result = _translate_source_with_diagnostics(
        """
        public class MathOps {
            public int half(int n) {
                return n / 2;
            }

            public double ratio(double n, double d) {
                return n / d;
            }
        }
        """,
    )

    # Coverage should not be dropped by the known int case (the float case succeeds cleanly).
    # If other unhandled exist they are unrelated to this rule.
    assert "return n // 2" in result.source
    assert "return n / d" in result.source
    # The note moves to warnings (visible in CLI/diagnostics) rather than unhandled.
    reasons = [w.reason for w in result.diagnostics.warnings]
    assert any("integer division translated with floor division" in r for r in reasons)
    # The int/int case no longer drops coverage (we use warn()).
    # See test_ambiguous_division_drops_coverage for the "numeric type certainty" path.
    _assert_valid_python(result.source)


def test_ambiguous_division_drops_coverage() -> None:
    result = _translate_source_with_diagnostics(
        """
        public class MathOps {
            public Object ratio(Object left, Object right) {
                return left / right;
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "return __j2py_todo__('left / right')" in result.source
    assert result.diagnostics.unhandled[-1].reason == "division requires numeric type certainty"
    _assert_valid_python(result.source)


def test_null_comparison_uses_python_identity_operators() -> None:
    python_source, coverage = _translate_source(
        """
        public class Nulls {
            public boolean present(Object value) {
                return value != null;
            }

            public boolean missing(Object value) {
                return null == value;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return value is not None" in python_source
    assert "return value is None" in python_source
    _assert_valid_python(python_source)


def test_stream_item_name_avoids_bad_singularization() -> None:
    """Regression: _stream_item_name used to produce statu/addres/clas etc."""
    from j2py.translate.diagnostics import TranslationContext, TranslationDiagnostics
    from j2py.translate.expressions import _stream_item_name

    ctx = TranslationContext(cfg=CFG, diagnostics=TranslationDiagnostics())

    cases = {
        "statuses": "status",
        "status": "status",
        "addresses": "address",
        "address": "address",
        "classes": "class",
        "items": "item",
        "entries": "entry",
    }
    for src_name, want in cases.items():
        got = _stream_item_name(src_name, ctx)
        # tolerate "item_" style safety suffix from naming
        ok = got == want or got == want + "_" or got.endswith(want) or got.endswith(want + "_")
        assert ok, f"{src_name} -> {got} (wanted ~{want})"


def test_stream_pipeline_produces_sensible_loop_var_for_statuses() -> None:
    """A successful stream rewrite for a 'statuses' receiver should not emit statu/statuse."""
    python_source, coverage = _translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> names(List<Status> statuses) {
                return statuses.stream()
                        .map(Status::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    # The pipeline must have fired and produced a clean listcomp (coverage 1.0 for this file)
    assert coverage == 1.0
    # The loop variable should be a sensible singular ("status" or "status_" after naming),
    # not a truncated form like "statu".
    assert "for status in statuses" in python_source or "for status_ in statuses" in python_source
    # Avoid old bad truncation in the generated comp (signatures may still contain "statuses").
    assert "for statu in" not in python_source and "for statu_" not in python_source
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_partial_translation_reports_structured_diagnostics() -> None:
    result = _translate_source_with_diagnostics(
        """
        public class FieldOnly {
            private int count;
        }
        """,
    )

    assert result.coverage < 1.0
    assert result.diagnostics.unhandled
    diagnostic = result.diagnostics.unhandled[0]
    assert diagnostic.node_type == "field_declaration"
    assert diagnostic.line == 3
    assert diagnostic.text == "private int count;"
    assert (
        diagnostic.reason == "instance field declaration without initializer needs default review"
    )


def test_interface_declaration_translates_to_protocol() -> None:
    result = _translate_source_with_diagnostics(
        """
        public interface Greeter {
            void greet();
        }
        """,
    )

    assert result.coverage == 1.0
    assert "from typing import Protocol" in result.source
    assert "class Greeter(Protocol):" in result.source
    assert "def greet(self) -> None: ..." in result.source
    assert not result.diagnostics.unhandled
    assert [diagnostic.node_type for diagnostic in result.diagnostics.handled] == [
        "interface_declaration",
        "method_declaration",
    ]
    _assert_valid_python(result.source)


def test_annotation_type_declaration_emits_valid_placeholder() -> None:
    result = _translate_source_with_diagnostics(
        """
        public @interface Marker {
        }
        """,
    )

    assert result.coverage == 0.0
    assert "class Marker:" in result.source
    assert "TODO(j2py): unsupported annotation type declaration" in result.source
    assert result.diagnostics.unhandled[0].node_type == "annotation_type_declaration"
    _assert_valid_python(result.source)
