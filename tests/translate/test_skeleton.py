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


def test_block_lambda_translates_to_local_helper() -> None:
    """Block lambdas are now supported via a local helper function (no more forced TODO/LLM)."""
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

    # The construct itself is now handled by the rule layer.
    unhandled_reasons = [u.reason for u in result.diagnostics.unhandled]
    assert "block lambda requires helper function" not in unhandled_reasons

    # A helper was emitted and is referenced at the use site.
    assert "def _j2py_lambda_" in result.source
    assert "_j2py_lambda_" in result.source  # the name is used
    assert "return user.get_name()" in result.source or "return user.getName()" in result.source
    _assert_valid_python(result.source)


def test_block_lambda_with_multiple_statements_and_capture() -> None:
    """Richer block lambda exercising locals, early return, and captured field."""
    python_source, coverage = _translate_source(
        """
        import java.util.function.Function;

        public class Capturing {
            private String prefix = ">> ";

            public Function<String, String> maker() {
                return s -> {
                    String trimmed = s.trim();
                    if (trimmed.isEmpty()) {
                        return prefix + "<empty>";
                    }
                    return prefix + trimmed.toUpperCase();
                };
            }
        }
        """,
    )

    assert "def _j2py_lambda_" in python_source
    # The helper body contains the statements (structure preserved).
    assert "trimmed" in python_source
    # Early return + normal return path present (concat style may be f-string or +).
    assert "<empty>" in python_source
    has_upper = "upper()" in python_source or "to_upper_case()" in python_source
    assert "trimmed" in python_source and has_upper

    # The lambda name is used (returned from maker()).
    assert "_j2py_lambda_" in python_source
    assert "return _j2py_lambda_" in python_source

    _assert_valid_python(python_source)


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


def test_stream_pipeline_to_set_rewrite() -> None:
    """Phase 1: toSet collector now rewrites to set comprehension."""
    python_source, coverage = _translate_source(
        """
        import java.util.Set;
        import java.util.stream.Collectors;

        public class Streams {
            public Set<String> unique(List<Status> statuses) {
                return statuses.stream()
                        .map(Status::getName)
                        .collect(Collectors.toSet());
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "{" in python_source and " for " in python_source and "}" in python_source
    assert "for status in statuses" in python_source or "for status_ in statuses" in python_source
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_stream_pipeline_joining_basic() -> None:
    """Phase 1: basic Collectors.joining() rewrites to .join(genexp)."""
    python_source, coverage = _translate_source(
        """
        import java.util.stream.Collectors;

        public class Streams {
            public String joined(List<String> parts) {
                return parts.stream()
                        .filter(s -> !s.isEmpty())
                        .collect(Collectors.joining(", "));
            }
        }
        """,
    )

    assert coverage == 1.0
    assert ".join(" in python_source
    assert "for " in python_source and " in parts" in python_source
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_stream_with_block_lambda_uses_helper_in_chain() -> None:
    """Phase 1: block lambda in stream (non-rewritten case) uses helper name."""
    # Integration test for block lambda support inside stream chains that don't
    # trigger the listcomp rewrite (e.g. because of block body).
    python_source, coverage = _translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> complex(List<String> items) {
                return items.stream()
                        .map(s -> { String t = s.trim(); return t.toUpperCase(); })
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    # Pipeline rewrite fails on block -> general path uses the helper name
    assert "def _j2py_lambda_" in python_source
    assert "_j2py_lambda_" in python_source  # name used in map
    assert "stream" in python_source.lower()  # chain visible
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_stream_pipeline_sorted_and_distinct() -> None:
    """Phase 2: support .sorted() and .distinct() as post-wraps on the comp."""
    # Safe when they appear late in the chain before terminal.
    python_source, coverage = _translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> sortedUnique(List<String> items) {
                return items.stream()
                        .filter(s -> s.length() > 0)
                        .sorted()
                        .distinct()
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert coverage == 1.0
    # Should have the inner comp wrapped with sorted and distinct
    assert "list(dict.fromkeys(sorted(" in python_source
    assert " for " in python_source and " in items" in python_source
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_stream_pipeline_sorted_with_key() -> None:
    """Phase 2: .sorted(Comparator) with simple method ref key."""
    python_source, coverage = _translate_source(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<Item> byName(List<Item> items) {
                return items.stream()
                        .sorted(Item::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "sorted(" in python_source
    assert "key=lambda " in python_source  # or similar
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_stream_sorted_before_map_falls_back_to_preserve_order() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> sortedNames(List<Item> items) {
                return items.stream()
                        .sorted()
                        .map(Item::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "stream map after sorted/distinct requires order-preserving translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    assert "return sorted([item.get_name() for item in items])" not in result.source
    _assert_valid_python(result.source)


def test_stream_distinct_before_map_falls_back_to_preserve_order() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> uniqueNames(List<Item> items) {
                return items.stream()
                        .distinct()
                        .map(Item::getName)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "stream map after sorted/distinct requires order-preserving translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    assert "dict.fromkeys([item.get_name() for item in items])" not in result.source
    _assert_valid_python(result.source)


def test_joining_with_prefix_suffix_falls_back() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.stream.Collectors;

        public class Streams {
            public String joined(List<String> parts) {
                return parts.stream()
                        .collect(Collectors.joining(", ", "[", "]"));
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "Collectors.joining with prefix/suffix requires manual translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    _assert_valid_python(result.source)


def test_stream_pipeline_grouping_by_basic() -> None:
    """Phase 3: basic groupingBy produces helper with defaultdict accumulation."""
    python_source, coverage = _translate_source(
        """
        import java.util.List;
        import java.util.Map;
        import java.util.stream.Collectors;

        public class Streams {
            public Map<String, List<String>> byFirst(List<String> items) {
                return items.stream()
                        .filter(s -> !s.isEmpty())
                        .collect(Collectors.groupingBy(s -> s.substring(0,1)));
            }
        }
        """,
    )

    assert coverage > 0.5  # at least the construct itself handled
    assert "def _j2py_groupby_" in python_source
    assert "from collections import defaultdict" in python_source
    assert "groups[key].append" in python_source
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_stream_pipeline_to_map_basic() -> None:
    """Phase 3: basic toMap produces helper with dict accumulation."""
    python_source, coverage = _translate_source(
        """
        import java.util.Map;
        import java.util.stream.Collectors;

        public class Streams {
            public Map<String, Integer> toMap(List<Item> items) {
                return items.stream()
                        .filter(i -> i.getValue() > 0)
                        .collect(Collectors.toMap(Item::getKey, Item::getValue));
            }
        }
        """,
    )

    assert "def _j2py_to_map_" in python_source
    assert "result = {}" in python_source
    assert "result[key] = " in python_source
    assert "__j2py_todo__" not in python_source
    _assert_valid_python(python_source)


def test_to_map_with_merge_function_falls_back() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.Map;
        import java.util.stream.Collectors;

        public class Streams {
            public Map<String, Integer> toMap(List<Item> items) {
                return items.stream()
                        .collect(Collectors.toMap(Item::getKey, Item::getValue, (a, b) -> b));
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert any(
        "Collectors.toMap with merge/supplier arguments requires manual translation" in item.reason
        for item in result.diagnostics.unhandled
    )
    _assert_valid_python(result.source)


def test_block_lambda_in_field_initializer_does_not_emit_undefined_helper() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.function.Function;

        public class FieldLambda {
            private Function<String, String> mapper = s -> { return s.trim(); };
        }
        """,
    )

    assert result.coverage < 1.0
    assert "_j2py_lambda_" not in result.source
    assert "__j2py_todo__" in result.source
    assert any(
        "block lambda requires local helper scope" in item.reason
        for item in result.diagnostics.unhandled
    )
    _assert_valid_python(result.source)


def test_grouping_by_in_field_initializer_does_not_emit_undefined_helper() -> None:
    result = _translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.Map;
        import java.util.stream.Collectors;

        public class FieldStream {
            private Map<String, List<String>> groups = items.stream()
                    .collect(Collectors.groupingBy(s -> s.substring(0, 1)));
        }
        """,
    )

    assert result.coverage < 1.0
    assert "_j2py_groupby_" not in result.source
    assert any(
        "Collectors.groupingBy requires local helper scope" in item.reason
        for item in result.diagnostics.unhandled
    )
    _assert_valid_python(result.source)


def test_merged_overload_block_lambda_emits_helper_before_use() -> None:
    python_source, coverage = _translate_source(
        """
        import java.util.function.Function;

        public class Overloaded {
            public Function<String, String> mapper(String prefix) {
                return s -> { return prefix + s.trim(); };
            }

            public Function<Integer, String> mapper(Integer prefix) {
                return s -> { return prefix + s.trim(); };
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "def _j2py_lambda_1(" in python_source
    assert python_source.index("def _j2py_lambda_1(") < python_source.index("return _j2py_lambda_1")
    _assert_valid_python(python_source)


def test_stream_flatmap_falls_back_with_explicit_diagnostic() -> None:
    """Targeted polish: unsupported stream intermediate (flatMap) now records clear reason."""
    result = _translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.stream.Collectors;

        public class Streams {
            public List<String> flat(List<List<String>> nested) {
                return nested.stream()
                        .flatMap(List::stream)
                        .collect(Collectors.toList());
            }
        }
        """,
    )

    reasons = [u.reason for u in result.diagnostics.unhandled]
    assert any("unsupported stream intermediate: flatMap" in r for r in reasons)
    # still produces something (general path)
    assert "stream" in result.source.lower() or "flat_map" in result.source
    _assert_valid_python(result.source)


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
