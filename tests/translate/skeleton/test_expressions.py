"""Skeleton translator tests — expressions, literals, and calls."""

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.translate.skeleton.helpers import (
    CFG,
    FIXTURES,
    assert_valid_python,
    translate_source,
    translate_source_with_diagnostics,
)


def test_comments_and_dropped_annotations_do_not_reduce_coverage() -> None:
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)


def test_unsupported_annotations_are_warnings_not_unhandled() -> None:
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)


def test_same_class_static_field_reads_are_qualified_in_methods() -> None:
    result = translate_source_with_diagnostics(
        """
        public class StaticFields {
            private static final int COUNT = 1;
            private static final int DOUBLE = COUNT + 1;

            public static int count() {
                return COUNT;
            }

            public int instanceCount() {
                return COUNT;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "    COUNT: int = 1" in result.source
    assert "    DOUBLE: int = COUNT + 1" in result.source
    assert "return StaticFields.COUNT" in result.source
    assert "return COUNT" not in result.source
    assert_valid_python(result.source)


def test_bitwise_comparison_operands_are_parenthesized() -> None:
    result = translate_source_with_diagnostics(
        """
        public class BitwiseComparisons {
            public static boolean any(Object left, Object middle, Object right) {
                return left != null | middle != null || right != null;
            }

            public static boolean anyParenthesized(Object left, Object middle, Object right) {
                return (left != null) | (middle != null) || right != null;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "return (left is not None) | (middle is not None) or right is not None" in result.source
    assert (
        result.source.count(
            "return (left is not None) | (middle is not None) or right is not None",
        )
        == 2
    )
    assert_valid_python(result.source)


def test_generic_cast_to_translated_class_uses_string_target() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Casts<T> {
            public boolean same(Object obj) {
                Casts<?> other = (Casts<?>) obj;
                return other != null;
            }

            public Casts<T>[] array(Object obj) {
                return (Casts<T>[]) obj;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "other = cast('Casts[Any]', obj)" in result.source
    assert "return cast('list[Casts[T]]', obj)" in result.source
    assert_valid_python(result.source)


def test_char_arithmetic_wraps_operands_in_ord() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Chars {
            public char nextChar(char c) {
                return (char) (c + 1);
            }

            public int charCode(char c) {
                return c + 0;
            }

            public char toUpper(char c) {
                return (char) (c - 32);
            }

            public int distance(char a, char b) {
                return b - a;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "__j2py_todo__" not in result.source
    # char + int / char - int wrap the char operand in ord(); narrowing cast adds chr().
    assert "chr(int(ord(c) + 1) & 0xFFFF)" in result.source
    assert "return ord(c) + 0" in result.source
    assert "chr(int(ord(c) - 32) & 0xFFFF)" in result.source
    # char - char: both operands wrapped.
    assert "return ord(b) - ord(a)" in result.source
    assert all(
        "char arithmetic translated with ord()" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_char_arithmetic_runs_without_type_error() -> None:
    """Acceptance criterion: translated char arithmetic must not raise TypeError."""
    source, coverage = translate_source(
        """
        public class Chars {
            public char nextChar(char c) {
                return (char) (c + 1);
            }

            public int charCode(char c) {
                return c + 0;
            }

            public char toUpper(char c) {
                return (char) (c - 32);
            }
        }
        """,
    )

    assert coverage == 1.0
    namespace: dict[str, object] = {}
    exec(compile(source, "<chars>", "exec"), namespace)
    chars = namespace["Chars"]()  # type: ignore[operator]
    assert chars.next_char("a") == "b"
    assert chars.char_code("a") == 97
    assert chars.to_upper("a") == "A"


def test_static_standard_library_methods_translate_to_python_equivalents() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;

        public class StaticStdlib {
            public int absValue(int value) {
                return Math.abs(value);
            }

            public int maxValue(int left, int right) {
                return Math.max(left, right);
            }

            public int minValue(int left, int right) {
                return Math.min(left, right);
            }

            public double power(double base, double exponent) {
                return Math.pow(base, exponent);
            }

            public double rounded(double value) {
                return Math.round(value);
            }

            public double roots(double value) {
                return Math.sqrt(value) + Math.floor(value) + Math.ceil(value) + Math.log(value);
            }

            public double constants() {
                return Math.PI + Math.E;
            }

            public int parse(String value) {
                return Integer.parseInt(value);
            }

            public int parseRadix(String value) {
                return Integer.parseInt(value, 16);
            }

            public int integerValue(Object value) {
                return Integer.valueOf(value);
            }

            public String integerStrings(int value) {
                return Integer.toString(value)
                        + Integer.toBinaryString(value)
                        + Integer.toHexString(value);
            }

            public int maxInteger() {
                return Integer.MAX_VALUE;
            }

            public long longValue(String value) {
                return Long.parseLong(value);
            }

            public double doubleValue(String value) {
                return Double.parseDouble(value);
            }

            public String stringValue(Object value) {
                return String.valueOf(value);
            }

            public String formatted(String name, int count) {
                return String.format("%s:%d", name, count);
            }

            public List<String> asList(String first, String second) {
                return Arrays.asList(first, second);
            }

            public Object stream(List<String> values) {
                return Arrays.stream(values);
            }

            public List<String> immutable(List<String> values) {
                return Collections.unmodifiableList(values);
            }

            public boolean missing(Object value) {
                return Objects.isNull(value);
            }

            public boolean present(Object value) {
                return Objects.nonNull(value);
            }

            public Object required(Object value) {
                return Objects.requireNonNull(value);
            }

            public void sortValues(List<Integer> values) {
                Collections.sort(values);
                Collections.reverse(values);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "import math" in result.source
    expected_fragments = (
        "return abs(value)",
        "return max(left, right)",
        "return min(left, right)",
        "return pow(base, exponent)",
        "return math.floor(value + 0.5)",
        "return math.sqrt(value) + math.floor(value) + math.ceil(value) + math.log(value)",
        "return math.pi + math.e",
        "return int(value)",
        "return int(value, 16)",
        "return str(value) + format(value, 'b') + format(value, 'x')",
        "return 2**31 - 1",
        "return float(value)",
        'return "%s:%d" % (name, count)',
        "return [first, second]",
        "return iter(values)",
        "return values",
        "return value is None",
        "return value is not None",
        "values.sort()",
        "values.reverse()",
    )
    for fragment in expected_fragments:
        assert fragment in result.source
    for unresolved in (
        "Math.",
        "Integer.",
        "Long.",
        "Double.",
        "String.",
        "Collections.",
        "Arrays.",
        "Objects.",
    ):
        assert unresolved not in result.source
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "Collections.unmodifiableList translated as original list; verify mutability",
    ]
    assert_valid_python(result.source)


def test_receiverless_static_sibling_method_calls_are_class_qualified() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CharChecks {
            public static boolean isAlpha(char ch) {
                return isAlphaUpper(ch) || isAlphaLower(ch);
            }

            public static boolean isAlphaUpper(char ch) {
                return ch >= 'A' && ch <= 'Z';
            }

            public static boolean isAlphaLower(char ch) {
                return ch >= 'a' && ch <= 'z';
            }
        }
        """,
    )

    assert "return CharChecks.is_alpha_upper(ch) or CharChecks.is_alpha_lower(ch)" in (
        result.source
    )
    assert "return is_alpha_upper(ch) or is_alpha_lower(ch)" not in result.source
    assert result.coverage == 1.0
    assert_valid_python(result.source)


def test_receiverless_static_calls_qualify_enclosing_class_from_nested_type() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Outer {
            public static int base(int value) {
                return value + 1;
            }

            public static class Inner {
                public static int run(int value) {
                    return base(value);
                }
            }
        }
        """,
    )

    assert "return Outer.base(value)" in result.source
    assert "return base(value)" not in result.source
    assert_valid_python(result.source)


def test_receiverless_static_calls_qualify_inherited_methods() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Base {
            public static int bump(int value) {
                return value + 1;
            }
        }

        public class Child extends Base {
            public static int run(int value) {
                return bump(value);
            }
        }
        """,
    )

    assert "return Base.bump(value)" in result.source
    assert "return bump(value)" not in result.source
    assert_valid_python(result.source)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("return Math.abs(left);", "return abs(left)"),
        ("return Math.max(left, right);", "return max(left, right)"),
        ("return Math.min(left, right);", "return min(left, right)"),
        ("return Math.pow(base, exponent);", "return pow(base, exponent)"),
        ("return Math.sqrt(base);", "return math.sqrt(base)"),
        ("return Math.floor(base);", "return math.floor(base)"),
        ("return Math.ceil(base);", "return math.ceil(base)"),
        ("return Math.round(base);", "return math.floor(base + 0.5)"),
        ("return Math.log(base);", "return math.log(base)"),
        ("return Math.PI;", "return math.pi"),
        ("return Math.E;", "return math.e"),
        ("return Integer.parseInt(text);", "return int(text)"),
        ("return Integer.parseInt(text, 16);", "return int(text, 16)"),
        ("return Integer.valueOf(value);", "return int(value)"),
        ("return Integer.toString(left);", "return str(left)"),
        ("return Integer.toBinaryString(left);", "return format(left, 'b')"),
        ("return Integer.toHexString(left);", "return format(left, 'x')"),
        ("return Integer.MAX_VALUE;", "return 2**31 - 1"),
        ("return Character.valueOf(ch);", "return ch"),
        ("return Character.toString(ch);", "return str(ch)"),
        ("return Long.parseLong(text);", "return int(text)"),
        ("return Double.parseDouble(text);", "return float(text)"),
        ("return String.valueOf(value);", "return str(value)"),
        ('return String.format("%s:%d", name, left);', 'return "%s:%d" % (name, left)'),
        (
            'return String.format(Locale.US, "%s:%d", name, left);',
            'return "%s:%d" % (name, left)',
        ),
        ("Collections.sort(values); return null;", "values.sort()"),
        ("Collections.reverse(values); return null;", "values.reverse()"),
        ("return Collections.unmodifiableList(values);", "return values"),
        ("return Arrays.asList(left, right);", "return [left, right]"),
        ("return Arrays.stream(values);", "return iter(values)"),
        ("return Objects.requireNonNull(value);", "return value"),
        ("return Objects.isNull(value);", "return value is None"),
        ("return Objects.nonNull(value);", "return value is not None"),
    ],
)
def test_static_standard_library_mapping_cases(body: str, expected: str) -> None:
    result = translate_source_with_diagnostics(
        f"""
        import java.util.List;
        import java.util.Locale;

        public class StaticStdlibCase {{
            public Object value(
                    Object value,
                    int left,
                    int right,
                    double base,
                    double exponent,
                    String text,
                    String name,
                    List<Integer> values) {{
                {body}
            }}
        }}
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert expected in result.source
    assert_valid_python(result.source)


def test_unknown_static_import_emits_todo_and_diagnostic() -> None:
    result = translate_source_with_diagnostics(
        """
        import static com.example.Helpers.magic;

        public class StaticImports {
            public int apply(int value) {
                return magic(value);
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "# TODO(j2py): static import com.example.Helpers.magic - resolve manually" in (
        result.source
    )
    assert result.diagnostics.unhandled[0].reason == (
        "unknown static import com.example.Helpers.magic"
    )
    # Unknown static method import now emits a qualified call so output stays syntactically
    # valid and reviewable; bare unqualified fallback was replaced by ClassName.method(args).
    assert "return Helpers.magic(value)" in result.source
    assert_valid_python(result.source)


def test_unknown_static_field_import_emits_qualified_identifier() -> None:
    result = translate_source_with_diagnostics(
        """
        import static com.example.BoundType.CLOSED;

        public class StaticField {
            public boolean check(Object x) {
                return x == CLOSED;
            }
        }
        """,
    )

    assert "# TODO(j2py): static import com.example.BoundType.CLOSED - resolve manually" in (
        result.source
    )
    # Unknown static field now emits qualified ClassName.MEMBER so output is valid Python.
    assert "BoundType.CLOSED" in result.source
    assert "x == BoundType.CLOSED" in result.source or "== BoundType.CLOSED" in result.source
    assert_valid_python(result.source)


def test_static_field_alias_currently_precedes_local_shadowing() -> None:
    result = translate_source_with_diagnostics(
        """
        import static java.lang.Math.PI;

        public class StaticImportAliasPrecedence {
            public double value() {
                double PI = 1.0;
                return PI;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "PI = 1.0" in result.source
    assert "return math.pi" in result.source
    assert "return PI" not in result.source
    assert_valid_python(result.source)


@pytest.mark.parametrize(
    ("static_import", "body", "expected"),
    [
        (
            "import static com.google.common.base.Preconditions.checkNotNull;",
            "return checkNotNull(value);",
            "return value",
        ),
        (
            "import static java.util.Objects.requireNonNull;",
            "return requireNonNull(value);",
            "return value",
        ),
        (
            "import static com.google.common.base.Preconditions.checkNotNull;",
            "this.value = checkNotNull(value);",
            "self.value = value",
        ),
        (
            "import static com.google.common.base.Preconditions.checkState;",
            'checkState(canRemove, "message");',
            'assert can_remove, "message"',
        ),
        (
            "import static com.google.common.base.Preconditions.checkArgument;",
            "checkArgument(size >= 0);",
            "assert size >= 0",
        ),
        (
            "import static com.google.common.base.Preconditions.checkState;",
            'checkState(index >= 0, "index %s out of range", index);',
            'assert index >= 0, "index %s out of range" % index',
        ),
    ],
)
def test_known_static_import_allowlist_cases(
    static_import: str,
    body: str,
    expected: str,
) -> None:
    result = translate_source_with_diagnostics(
        f"""
        {static_import}

        public class StaticImportAllowlist {{
            private Object value;

            public Object apply(Object value, boolean can_remove, int size) {{
                {body}
            }}
        }}
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert expected in result.source
    assert "# TODO(j2py): static import" not in result.source
    assert_valid_python(result.source)


def test_static_imports_resolve_inside_non_class_type_contexts_and_overloads() -> None:
    result = translate_source_with_diagnostics(
        """
        import static java.lang.Integer.MAX_VALUE;
        import static java.lang.Math.PI;
        import static java.lang.Math.sqrt;

        interface StaticImportInterface {
            default double circumference(double radius) {
                return 2 * PI * radius;
            }

            static double root(double value) {
                return sqrt(value);
            }
        }

        enum StaticImportEnum {
            ONE(PI);

            private final double value;

            StaticImportEnum(double value) {
                this.value = value;
            }

            public double limit() {
                return PI;
            }
        }

        @interface StaticImportAnnotation {
            int value() default MAX_VALUE;
        }

        class StaticImportOverload {
            public double value() {
                return PI;
            }

            public double value(int ignored) {
                return PI;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "return 2 * math.pi * radius" in result.source
    assert "return math.sqrt(value)" in result.source
    assert "ONE = math.pi" in result.source
    assert "return math.pi" in result.source
    assert "value: int = 2**31 - 1" in result.source
    assert "return pi" not in result.source
    assert_valid_python(result.source)


def test_char_comparison_is_not_rewritten() -> None:
    """Single-char str comparison matches Java numeric char ordering; leave it alone."""
    source, coverage = translate_source(
        """
        public class Chars {
            public boolean isUpper(char c) {
                return c >= 'A' && c <= 'Z';
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "ord(" not in source
    assert 'c >= "A"' in source
    assert 'c <= "Z"' in source


def test_char_comparison_with_numeric_wraps_in_ord() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Chars {
            public boolean isControl(char c) {
                return c < 32;
            }

            public boolean isZero(Character c) {
                return c == 0;
            }

            public boolean isNull(Character c) {
                return c == null;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return ord(c) < 32" in result.source
    assert "return ord(c) == 0" in result.source
    assert "return c is None" in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_char_numeric_comparison_runs_without_type_error() -> None:
    source, coverage = translate_source(
        """
        public class Chars {
            public boolean isControl(char c) {
                return c < 32;
            }

            public boolean isZero(Character c) {
                return c == 0;
            }
        }
        """,
    )

    assert coverage == 1.0
    namespace: dict[str, object] = {}
    exec(compile(source, "<chars>", "exec"), namespace)
    chars = namespace["Chars"]()  # type: ignore[operator]
    assert chars.is_control("\n") is True
    assert chars.is_control("A") is False
    assert chars.is_zero("\x00") is True
    assert chars.is_zero("A") is False


def test_compound_assignment_translates() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_prefix_and_postfix_updates_translate() -> None:
    python_source, coverage = translate_source(
        """
        public class Updates {
            public int apply(int value) {
                ++value;
                value++;
                --value;
                value--;
                return value;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert python_source.count("value += 1") == 2
    assert python_source.count("value -= 1") == 2
    assert "unsupported update operator" not in python_source
    assert_valid_python(python_source)


def test_update_expression_operator_search_ignores_comment_tokens() -> None:
    python_source, coverage = translate_source(
        """
        public class Updates {
            public int apply(int value) {
                /* prefix marker */ ++value;
                value /* postfix marker */ ++;
                return value;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert python_source.count("value += 1") == 2
    assert "unsupported update operator" not in python_source
    assert_valid_python(python_source)


def test_varargs_parameter_with_inline_comment_keeps_element_type() -> None:
    python_source, coverage = translate_source(
        """
        public class VarargsComments {
            public void names(/* caller labels */ String... labels) {
                System.out.println(labels.length);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "def names(self, *labels: str) -> None:" in python_source
    assert "block_comment" not in python_source
    assert_valid_python(python_source)


def test_hex_literals_inline_argument_comments_and_primitive_class_literals_translate() -> None:
    python_source, coverage = translate_source(
        """
        public class LowRisk {
            public Class<?> primitive() {
                return boolean.class;
            }

            public int mask() {
                return 0xFF;
            }

            public int longMask() {
                return 0xFFFFL;
            }

            public int octal() {
                return 0777;
            }

            public int underscoredOctal() {
                return 077_7;
            }

            public LowRisk() {
                super(/* latest api = */ 0x09);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return bool" in python_source
    assert "return 0xFF" in python_source
    assert "return 0xFFFF" in python_source
    assert "return 0o777" in python_source
    assert "return 0o77_7" in python_source
    assert "super().__init__(0x09)" in python_source
    assert "__j2py_todo__" not in python_source
    assert "unsupported expression block_comment" not in python_source
    assert_valid_python(python_source)


def test_array_type_class_literals_translate_to_runtime_comparable_types() -> None:
    result = translate_source_with_diagnostics(
        """
        public class ArrayTypeClassLiteral {
            public Class<?> primitive() {
                return boolean[].class;
            }

            public boolean isPrimitiveBooleanArray(Class<?> candidate) {
                return candidate == boolean[].class;
            }

            public boolean isStringArray(Class<?> candidate) {
                return candidate == String[].class;
            }

            public boolean isQualifiedStringArray(Class<?> candidate) {
                return candidate == java.lang.String[].class;
            }

            public boolean isPrimitiveIntMatrix(Class<?> candidate) {
                return candidate == int[][].class;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return list[bool]" in result.source
    assert "return candidate == list[bool]" in result.source
    assert "return candidate == list[str]" in result.source
    assert "return candidate == list[list[int]]" in result.source
    assert "java.lang.String" not in result.source
    assert not result.diagnostics.unhandled
    assert "__j2py_todo__" not in result.source
    assert_valid_python(result.source)

    namespace: dict[str, object] = {}
    exec(result.source, namespace)
    translated_class = namespace["ArrayTypeClassLiteral"]
    instance = translated_class()
    assert instance.primitive() == list[bool]
    assert instance.is_primitive_boolean_array(list[bool]) is True
    assert instance.is_primitive_boolean_array(list[int]) is False
    assert instance.is_string_array(list[str]) is True
    assert instance.is_qualified_string_array(list[str]) is True
    assert instance.is_primitive_int_matrix(list[list[int]]) is True


def test_text_block_string_literal_translates_to_python_triple_quoted_string() -> None:
    python_source, coverage = translate_source(
        '''
        public class TextBlocks {
            public String message() {
                return """
                    alpha\\s
                    beta\\
                    gamma
                    """;
            }
        }
        ''',
    )

    assert coverage == 1.0
    assert 'return """alpha \nbetagamma\n"""' in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)


def test_sized_array_creation_uses_java_default_values() -> None:
    python_source, coverage = translate_source(
        """
        public class Arrays {
            public boolean[] flags(int size) {
                return new boolean[size];
            }

            public double[] values(int size) {
                return new double[size];
            }

            public char[] chars(int size) {
                return new char[size];
            }

            public String[] names(int size) {
                return new String[size];
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return [False] * size" in python_source
    assert "return [0.0] * size" in python_source
    assert 'return ["\\0"] * size' in python_source
    assert "return [None] * size" in python_source
    assert_valid_python(python_source)


def test_multidimensional_array_creation_uses_nested_allocations() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Arrays {
            public int[][] matrix(int rows, int cols) {
                return new int[rows][cols];
            }

            public boolean[][] flags(int rows, int cols) {
                return new boolean[rows][cols];
            }

            public int[][][] cube(int planes, int rows, int cols) {
                return new int[planes][rows][cols];
            }

            public String[][] names(int rows, int cols) {
                return new String[rows][cols];
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return [[0] * cols for _ in range(rows)]" in result.source
    assert "return [[False] * cols for _ in range(rows)]" in result.source
    assert "return [[[0] * cols for _ in range(rows)] for _ in range(planes)]" in (result.source)
    assert "return [[None] * cols for _ in range(rows)]" in result.source
    assert "__j2py_todo__" not in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)

    namespace: dict[str, object] = {}
    exec(result.source, namespace)
    instance = namespace["Arrays"]()
    matrix = instance.matrix(2, 3)
    cube = instance.cube(2, 2, 3)
    assert matrix == [[0, 0, 0], [0, 0, 0]]
    assert matrix[0] is not matrix[1]
    assert cube == [
        [[0, 0, 0], [0, 0, 0]],
        [[0, 0, 0], [0, 0, 0]],
    ]
    assert cube[0] is not cube[1]
    assert cube[0][0] is not cube[0][1]


def test_common_spring_expression_shapes_translate() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_static_utility_contains_not_lowered_to_in() -> None:
    """contains lowering to `in` must be skipped for static utility receivers and super.

    Safe case:  collection.contains(element)  →  element in collection
    Unsafe cases (all would raise TypeError at runtime):
      - 2-arg static: StringUtils.contains(s, sub)  — class is not iterable
      - 1-arg static: MyUtils.contains(s)            — class is not iterable
      - super:        super.contains(x)              — super is not iterable
    """
    python_source, _ = translate_source(
        """
        public class Util {
            public static boolean twoArgStatic(String s) {
                return StringUtils.contains(s, '.');
            }
            public static boolean oneArgStatic(String s) {
                return MyUtils.contains(s);
            }
        }
        """
    )
    # Receiver is snake-cased (StringUtils → string_utils, MyUtils → my_utils)
    assert "string_utils.contains(" in python_source
    assert "in string_utils" not in python_source
    assert "my_utils.contains(" in python_source
    assert "in my_utils" not in python_source
    assert_valid_python(python_source)


def test_map_get_preserves_missing_key_semantics() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_list_get_uses_local_variable_type() -> None:
    """List.get(index) on a locally declared list rewrites to indexing."""
    python_source, coverage = translate_source(
        """
        import java.util.List;

        public class Calls {
            public String first(List<String> values) {
                List<String> copy = values;
                return copy.get(0);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return copy[0]" in python_source
    assert "copy.get(" not in python_source
    assert_valid_python(python_source)


def test_map_get_uses_local_variable_type() -> None:
    """Map.get(key) on a locally declared map keeps .get semantics."""
    python_source, coverage = translate_source(
        """
        import java.util.Map;

        public class Calls {
            public String lookup(Map<String, Object> values) {
                Map<String, Object> attrs = values;
                return attrs.get("mode");
            }
        }
        """,
    )

    assert coverage == 1.0
    assert 'return attrs.get("mode")' in python_source
    assert_valid_python(python_source)


def test_annotation_attributes_get_is_map_like() -> None:
    """Spring AnnotationAttributes.get(key) is treated as map-like."""
    python_source, coverage = translate_source(
        """
        import org.springframework.core.annotation.AnnotationAttributes;

        public class Calls {
            public Object mode(AnnotationAttributes candidate) {
                return candidate.get("mode");
            }
        }
        """,
    )

    assert coverage == 1.0
    assert 'return candidate.get("mode")' in python_source
    assert_valid_python(python_source)


def test_calendar_get_is_api_call() -> None:
    """Calendar.get(field) is an API method, not ambiguous collection access."""
    result = translate_source_with_diagnostics(
        """
        import java.util.Calendar;

        public class Calls {
            public int day(Calendar calendar) {
                return calendar.get(Calendar.DAY_OF_MONTH);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return calendar.get(Calendar.DAY_OF_MONTH)" in result.source
    assert "calendar[" not in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_buffer_and_atomic_get_receivers_are_api_calls() -> None:
    """ByteBuffer and atomic-array get(index) calls are API methods."""
    result = translate_source_with_diagnostics(
        """
        import java.nio.ByteBuffer;
        import java.util.concurrent.atomic.AtomicLongArray;
        import java.util.concurrent.atomic.AtomicReferenceArray;

        public class Calls {
            private ByteBuffer byteBuffer;
            private AtomicLongArray counts;

            public byte byteAt(int index) {
                return this.byteBuffer.get(index);
            }

            public long countAt(int index) {
                return this.counts.get(index);
            }

            public Object valueAt(AtomicReferenceArray<Object> values, int index) {
                return values.get(index);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return self.byte_buffer.get(index)" in result.source
    assert "return self.counts.get(index)" in result.source
    assert "return values.get(index)" in result.source
    assert "byte_buffer[index]" not in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_multi_value_map_get_is_map_like() -> None:
    """ProfileCondition-style MultiValueMap local uses .get without ambiguous diagnostic."""
    python_source, coverage = translate_source(
        """
        import org.springframework.util.MultiValueMap;

        public class ProfileCondition {
            public boolean matches(MultiValueMap attrs) {
                if (attrs != null) {
                    for (Object value : attrs.get("value")) {
                        return true;
                    }
                }
                return true;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert 'attrs.get("value")' in python_source
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)


def test_ambiguous_get_invocation_drops_coverage() -> None:
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)


def test_immutable_list_field_get_uses_indexing() -> None:
    python_source, coverage = translate_source(
        """
        import com.google.common.collect.ImmutableList;

        public class Holder {
            private final ImmutableList<String> delegateList;

            public String at(int index) {
                return delegateList.get(index);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return self.delegate_list[index]" in python_source
    assert_valid_python(python_source)


def test_delegate_multimap_get_is_map_like() -> None:
    python_source, coverage = translate_source(
        """
        import com.google.common.collect.ListMultimap;

        public abstract class Forwarding {
            protected abstract ListMultimap<String, String> delegate();

            public java.util.List<String> lookup(String key) {
                return delegate().get(key);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return self.delegate().get(key)" in python_source
    assert_valid_python(python_source)


def test_chained_declared_method_return_type_get_uses_indexing() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.lang.reflect.Method;
        import java.util.List;

        public class ChainedGetReceiverType {
            private Mapping mapping;

            public Method attribute(int attributeIndex) {
                return this.mapping.getAttributes().get(attributeIndex);
            }

            static class Mapping {
                private List<Method> attributes;

                List<Method> getAttributes() {
                    return this.attributes;
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return self.mapping.get_attributes()[attribute_index]" in result.source
    assert "get_attributes().get(" not in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_static_factory_get_chain_preserves_api_call() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.lang.annotation.Annotation;

        public class StaticFactoryGetChain {
            public Object lookup(Annotation annotation, Class<?> annotationType) {
                return MergedAnnotations.from(annotation).get(annotationType);
            }

            static class MergedAnnotations {
                static MergedAnnotations from(Annotation annotation) {
                    return new MergedAnnotations();
                }

                MergedAnnotation get(Class<?> annotationType) {
                    return new MergedAnnotation();
                }
            }

            static class MergedAnnotation {
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return MergedAnnotations.from_(annotation).get(annotation_type)" in result.source
    assert "MergedAnnotations.from_(annotation)[" not in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_unknown_chained_method_return_type_get_stays_ambiguous() -> None:
    result = translate_source_with_diagnostics(
        """
        public class ChainedUnknown {
            public Object attribute(Object mapping, int attributeIndex) {
                return mapping.getAttributes().get(attributeIndex);
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "mapping.get_attributes().get(attribute_index)" in result.source
    assert result.diagnostics.unhandled[-1].reason == (
        "ambiguous get invocation requires receiver collection type"
    )
    assert_valid_python(result.source)


def test_unknown_static_factory_get_chain_stays_ambiguous() -> None:
    result = translate_source_with_diagnostics(
        """
        public class UnknownFactoryGetChain {
            public Object lookup(Object annotationType) {
                return UnknownFactory.from().get(annotationType);
            }

            static class UnknownFactory {
                static UnknownFactory from() {
                    return new UnknownFactory();
                }
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "return UnknownFactory.from_().get(annotation_type)" in result.source
    assert result.diagnostics.unhandled[-1].reason == (
        "ambiguous get invocation requires receiver collection type"
    )
    assert_valid_python(result.source)


def test_require_non_null_field_get_is_api_call() -> None:
    python_source, coverage = translate_source(
        """
        import java.lang.reflect.Field;
        import java.util.Objects;

        public class Reflection {
            public static Object read(Field field, Object obj) {
                return Objects.requireNonNull(field, "field").get(obj);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert ".get(obj)" in python_source
    assert_valid_python(python_source)


def test_super_future_get_is_not_ambiguous() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.concurrent.Future;

        public class Proxy extends AbstractFutureProxy {
            public Object load(long timeout, java.util.concurrent.TimeUnit unit) {
                return super.get(timeout, unit);
            }
        }

        class AbstractFutureProxy implements Future<Object> {
            public Object get(long timeout, java.util.concurrent.TimeUnit unit) {
                return null;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return super().get(timeout, unit)" in python_source
    assert_valid_python(python_source)


def test_multi_arg_get_skips_collection_disambiguation() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.nio.ByteBuffer;

        public class Reader {
            private final ByteBuffer buffer;

            public void read(byte[] bytes, int off, int len) {
                buffer.get(bytes, off, len);
            }
        }
        """,
    )

    assert not any(
        item.reason == "ambiguous get invocation requires receiver collection type"
        for item in result.diagnostics.unhandled
    )
    assert "self.buffer.get(bytes_, off, len_)" in result.source
    assert_valid_python(result.source)


def test_static_map_field_get_is_map_like() -> None:
    """Static cache fields like BeanAnnotationHelper.beanNameCache use map .get()."""
    python_source, coverage = translate_source(
        """
        import java.util.Map;
        import java.lang.reflect.Method;

        public class BeanAnnotationHelper {
            private static final Map<Method, String> beanNameCache = null;

            public static String resolve(Method beanMethod) {
                return beanNameCache.get(beanMethod);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "bean_name_cache.get(bean_method)" in python_source
    assert_valid_python(python_source)


def test_nested_holder_map_field_get_is_map_like() -> None:
    """Nested holder fields like holder.methodInterceptors.get(...) stay map-like."""
    python_source, coverage = translate_source(
        """
        import java.util.Map;
        import java.lang.reflect.Method;

        public class ConcurrencyLimitBeanPostProcessor {
            private class ConcurrencyLimitInterceptor {
                public Object lookup(ConcurrencyThrottleHolder holder, Method method) {
                    return holder.methodInterceptors.get(method);
                }
            }

            private static class ConcurrencyThrottleHolder {
                public Map methodInterceptors;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "holder.method_interceptors.get(method)" in python_source
    assert_valid_python(python_source)


def test_class_keyed_registry_get_is_api_call() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;

        public class ClassKeyedRegistryGet {
            public int count(CustomizerRegistry registry) {
                int total = 0;
                for (Customizer customizer : registry.get(Customizer.class)) {
                    total += customizer.weight();
                }
                return total;
            }

            static class CustomizerRegistry {
                <T> List<T> get(Class<T> klass) {
                    return null;
                }
            }

            interface Customizer {
                int weight();
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "for customizer in registry.get(Customizer):" in result.source
    assert "registry[Customizer]" not in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_unknown_registry_class_literal_get_receiver_stays_ambiguous() -> None:
    result = translate_source_with_diagnostics(
        """
        public class UnknownClassKeyedGet {
            public Object lookup(Object registry) {
                return registry.get(Customizer.class);
            }

            interface Customizer {
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "return registry.get(Customizer)" in result.source
    assert result.diagnostics.unhandled[-1].reason == (
        "ambiguous get invocation requires receiver collection type"
    )
    assert_valid_python(result.source)


def test_inner_class_can_use_outer_map_field_get() -> None:
    """Inner classes can resolve enclosing map fields such as bytesCache.get(name)."""
    python_source, coverage = translate_source(
        """
        import java.util.Map;

        public class ContextTypeMatchClassLoader {
            private final Map<String, byte[]> bytesCache = null;

            private class ContextOverridingClassLoader {
                public byte[] load(String name) {
                    return bytesCache.get(name);
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "bytes_cache.get(name)" in python_source
    assert_valid_python(python_source)


def test_reflect_field_get_is_api_call() -> None:
    """Field.get(instance) is a reflection API call, not list/map indexing."""
    python_source, coverage = translate_source(
        """
        import java.lang.reflect.Field;

        public class JBossLoadTimeWeaver {
            public Object read(Field transformer, ClassLoader classLoader) throws Exception {
                return transformer.get(classLoader);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "transformer.get(class_loader)" in python_source
    assert_valid_python(python_source)


def test_scheduled_future_get_is_api_call() -> None:
    """ScheduledFuture.get() is a blocking future API call."""
    python_source, coverage = translate_source(
        """
        import java.util.concurrent.ScheduledFuture;
        import java.util.concurrent.TimeUnit;

        public class ReschedulingRunnable {
            public Object await(ScheduledFuture<?> future, long timeout,
                    TimeUnit unit) throws Exception {
                return future.get(timeout, unit);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "future.get(timeout, unit)" in python_source
    assert_valid_python(python_source)


def test_class_style_get_invocation_preserves_static_factory_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Calls {
            public Object type(Class<?> value) {
                return ClassName.get(value);
            }

            public Object qualified(Class<?> value) {
                return com.example.ClassName.get(value);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return class_name.get(value)" in result.source
    assert "return com.example.class_name.get(value)" in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_equals_invocation_translates_to_python_equality() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_objects_equals_static_two_arg() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.Objects;

        public class Equals {
            public boolean same(String a, String b) {
                return Objects.equals(a, b);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return a == b" in python_source
    assert_valid_python(python_source)


def test_arrays_equals_static_two_arg() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.Arrays;

        public class CompoundOrdering {
            public boolean same(int[] left, int[] right) {
                return Arrays.equals(left, right);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return left == right" in python_source
    assert_valid_python(python_source)


def test_static_import_equals_two_arg() -> None:
    python_source, coverage = translate_source(
        """
        import static java.util.Objects.equals;

        public class MutableObject {
            public boolean same(Object left, Object right) {
                return equals(left, right);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return left == right" in python_source
    assert_valid_python(python_source)


def test_type_utils_equals_static_two_arg() -> None:
    python_source, coverage = translate_source(
        """
        public class TypeLiteral {
            public boolean same(Object value, Object other) {
                return org.apache.commons.lang3.reflect.TypeUtils.equals(value, other.value);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "return value == other.value" in python_source
    assert_valid_python(python_source)


def test_expression_lambdas_and_method_references_translate() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_block_lambda_translates_to_local_helper() -> None:
    """Block lambdas are now supported via a local helper function (no more forced TODO/LLM)."""
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)


def test_block_lambda_with_multiple_statements_and_capture() -> None:
    """Richer block lambda exercising locals, early return, and captured field."""
    python_source, coverage = translate_source(
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

    assert_valid_python(python_source)


def test_array_constructor_method_reference_in_to_array_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;

        public class FunctionalCallbacks {
            public String[] names(List<String> names) {
                return names.toArray(String[]::new);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return list(names)" in result.source
    assert "__j2py_todo__" not in result.source
    assert not result.diagnostics.unhandled
    assert [warning.reason for warning in result.diagnostics.warnings] == [
        "array constructor method reference translated as list factory",
    ]
    assert_valid_python(result.source)


def test_generic_type_constructor_reference_strips_type_args() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Foo {
            public void m() {
                Collector.of(ImmutableState<R, C, V>::new, s -> s.build());
            }
        }
        """,
    )
    assert "ImmutableState<R, C, V>" not in result.source
    assert "ImmutableState" in result.source
    assert_valid_python(result.source)


def test_emit_line_comments_flag_suppresses_preserved_comments() -> None:
    cfg = CFG.model_copy(update={"emit_line_comments": False})
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)


def test_emit_docstrings_flag_keeps_javadocs_as_comments() -> None:
    cfg = CFG.model_copy(update={"emit_docstrings": False})
    result = translate_source_with_diagnostics(
        """
        /**
         * Class docs.
         */
        public class Comments {
            /**
             * Method docs.
             *
             * @param value input value
             * @return output value
             */
            public String value(String value) {
                return value;
            }
        }
        """,
        cfg=cfg,
    )

    assert '"""Class docs.' not in result.source
    assert '"""Method docs.' not in result.source
    assert "# Class docs." in result.source
    assert "# Method docs." in result.source
    assert "# @param value input value" in result.source
    assert "# @return output value" in result.source
    assert result.coverage == 1.0
    assert_valid_python(result.source)


def test_emit_type_hints_flag_suppresses_standard_annotations() -> None:
    cfg = CFG.model_copy(update={"emit_type_hints": False})
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_string_concat_with_nested_quoted_expression_remains_valid_python() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_string_concat_preserves_leading_numeric_addition() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_integer_division_uses_floor_div_and_records_review_warning() -> None:
    """int/int division now uses warn() (proportionate) instead of unhandled record.
    We still produce correct // and surface the truncation note for reviewers,
    but we do not penalize coverage or force the LLM for a fully mechanical case.
    """
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)


def test_ambiguous_division_drops_coverage() -> None:
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)


def test_field_compound_integer_division_uses_truncating_helper() -> None:
    result = translate_source_with_diagnostics(
        """
        public class MathOps {
            private int count;

            public void shrink() {
                this.count /= 2;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "from j2py_runtime import _j2py_idiv" in result.source
    assert "self.count = _j2py_idiv(self.count, 2)" in result.source
    assert "self.count /=" not in result.source
    assert any(
        "integer compound division translated with truncating division" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_field_type_inference_preserves_nested_integer_division_and_long_shift() -> None:
    result = translate_source_with_diagnostics(
        """
        public class MathOps {
            static class Box {
                int count;
                long wide;
            }

            private Box box;

            public int halfBoxCount() {
                return box.count / 2;
            }

            public long shiftBoxWide() {
                return box.wide >>> 4;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return self.box.count // 2" in result.source
    assert "return (self.box.wide & 0xFFFFFFFFFFFFFFFF) >> (4 & 0x3F)" in result.source
    assert "__j2py_todo__" not in result.source
    assert not result.diagnostics.unhandled
    assert_valid_python(result.source)


def test_division_type_inference_reaches_method_and_function_returns() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.function.Function;

        public class MathOps {
            private Function<String, Integer> parser;

            public int localHalf() {
                return value() / 2;
            }

            public int parsedHalf(String text) {
                return parser.apply(text) / 2;
            }

            private int value() {
                return 6;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return self.value() // 2" in result.source
    assert "return self.parser.apply(text) // 2" in result.source
    assert "__j2py_todo__" not in result.source
    assert_valid_python(result.source)


def test_ternary_and_object_creation_type_inference_keep_float_and_int_division_distinct() -> None:
    result = translate_source_with_diagnostics(
        """
        public class MathOps {
            static class Box {
                int count;
            }

            public int halfNewBoxCount() {
                return new Box().count / 2;
            }

            public double halfChoice(boolean flag) {
                return (flag ? 1 : 2.0) / 2;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return MathOps.Box().count // 2" in result.source
    assert "return (1 if flag else 2.0) / 2" in result.source
    assert "return (1 if flag else 2.0) // 2" not in result.source
    assert_valid_python(result.source)


def test_nested_parentheses_around_division_operands_preserve_grouping() -> None:
    result = translate_source_with_diagnostics(
        """
        public class MathOps {
            public double halfChoice(boolean flag) {
                return ((flag ? 1 : 2.0)) / 2;
            }

            public double halfSwitch(int value) {
                return ((switch (value) { case 0 -> 4.0; default -> 8.0; })) / 2.0;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return (1 if flag else 2.0) / 2" in result.source
    assert "return 1 if flag else 2.0 / 2" not in result.source
    assert "return (4.0 if value == 0 else 8.0) / 2.0" in result.source
    assert "return 4.0 if value == 0 else 8.0 / 2.0" not in result.source
    assert_valid_python(result.source)


def test_switch_expression_division_operand_preserves_grouping() -> None:
    result = translate_source_with_diagnostics(
        """
        public class MathOps {
            public double halfSwitch(int value) {
                return (switch (value) { case 0 -> 4.0; default -> 8.0; }) / 2.0;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return (4.0 if value == 0 else 8.0) / 2.0" in result.source
    assert "return 4.0 if value == 0 else 8.0 / 2.0" not in result.source
    assert_valid_python(result.source)


def test_doubly_parenthesized_ternary_division_keeps_grouping() -> None:
    result = translate_source_with_diagnostics(
        """
        public class MathOps {
            public double halfChoice(boolean flag) {
                return ((flag ? 1 : 2.0)) / 2;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return (1 if flag else 2.0) / 2" in result.source
    assert_valid_python(result.source)


def test_unsigned_right_shift_variants_keep_masks_and_warnings_visible() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Shifts {
            private long bits;
            private int[] values;

            public long shiftLong(long input) {
                return input >>> 3;
            }

            public int shiftUnknown(Object input) {
                return input >>> 1;
            }

            public void shiftField() {
                this.bits >>>= 2;
            }

            public void shiftArray() {
                values[0] >>>= 1;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return (input_ & 0xFFFFFFFFFFFFFFFF) >> (3 & 0x3F)" in result.source
    assert "return (input_ & 0xFFFFFFFF) >> (1 & 0x1F)" in result.source
    assert (
        "_j2py_val = self.bits; self.bits = (_j2py_val & 0xFFFFFFFFFFFFFFFF) >> (2 & 0x3F)"
    ) in result.source
    assert (
        "_j2py_idx = 0; self.values[_j2py_idx] = "
        "(self.values[_j2py_idx] & 0xFFFFFFFF) >> (1 & 0x1F)"
    ) in result.source
    assert any(
        warning.reason == "unsigned right shift assumed 32-bit int width; verify operand type"
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_null_comparison_uses_python_identity_operators() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_stream_with_block_lambda_uses_helper_in_chain() -> None:
    """Phase 1: block lambda in stream (non-rewritten case) uses helper name."""
    # Integration test for block lambda support inside stream chains that don't
    # trigger the listcomp rewrite (e.g. because of block body).
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_multidimensional_array_creation_reports_full_coverage() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Arrays {
            public int[][] matrix(int rows, int cols) {
                return new int[rows][cols];
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert result.source.count("__j2py_todo__") == 0
    assert result.source.count("[[0] * cols for _ in range(rows)]") == 1
    assert not result.diagnostics.unhandled


def test_partially_unsized_array_creation_stays_unsupported() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Arrays {
            public int[][] jagged(int rows) {
                return new int[rows][];
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "__j2py_todo__('new int[rows][]')" in result.source
    assert result.diagnostics.unhandled[0].reason == (
        "array creation with unsized dimensions requires allocation handling"
    )
    assert_valid_python(result.source)


def test_interface_default_and_static_methods_translate_to_protocol_bodies() -> None:
    result = translate_source_with_diagnostics(
        """
        public interface Greeter {
            void greet(String name);

            default String greeting(String name) {
                return "Hello " + name;
            }

            default String repeat(String name) {
                greet(name);
                return greeting(name);
            }

            static String systemName() {
                return "j2py";
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "from typing import Protocol" in result.source
    assert "class Greeter(Protocol):" in result.source
    assert "def greet(self, name: str) -> None: ..." in result.source
    assert "def greeting(self, name: str) -> str:" in result.source
    assert 'return f"Hello {name}"' in result.source
    assert "self.greet(name)" in result.source
    assert "return self.greeting(name)" in result.source
    assert "@staticmethod" in result.source
    assert "def system_name() -> str:" in result.source
    assert 'return "j2py"' in result.source
    assert not result.diagnostics.unhandled
    assert any(
        diagnostic.reason == "translated interface default method"
        for diagnostic in result.diagnostics.handled
    )
    assert any(
        diagnostic.reason == "translated interface static method"
        for diagnostic in result.diagnostics.handled
    )
    assert_valid_python(result.source)


def test_super_method_receiver_translates_to_super_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Base {
            void endClass() {}
            Object getGenerator(Object resource) { return resource; }
            void setTarget(Object target) {}
            boolean cancel(boolean mayInterrupt) { return mayInterrupt; }
        }

        public class Child extends Base {
            void finish() {
                super.endClass();
            }

            Object generator(Object resource) {
                return super.getGenerator(resource);
            }

            void configure(Object target) {
                super.setTarget(target);
            }

            boolean cancel(boolean mayInterrupt) {
                return super.cancel(mayInterrupt);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert not any(
        "unsupported expression super" in diagnostic.reason
        for diagnostic in result.diagnostics.unhandled
    )
    assert "super().end_class()" in result.source
    assert "return super().get_generator(resource)" in result.source
    assert "super().set_target(target)" in result.source
    assert "return super().cancel(may_interrupt)" in result.source
    assert any(
        diagnostic.reason == "translated super expression"
        for diagnostic in result.diagnostics.handled
    )
    assert_valid_python(result.source)


def test_super_method_calls_corpus_construct_reaches_full_coverage() -> None:
    parsed = parse_file(FIXTURES / "corpus" / "constructs" / "SuperMethodCalls.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "super().end_class()" in result.source
    assert "return super().get_generator(resource)" in result.source
    assert_valid_python(result.source)


def test_primitive_int_cast_emits_int_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public int narrow(double x) { return (int) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "return int(x)  # cast: (int) - numeric narrowing" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_primitive_long_cast_emits_int_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public long widen(int x) { return (long) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return int(x)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_primitive_byte_cast_emits_signed_narrowing() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public byte truncate(int x) { return (byte) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return ((int(x) & 0xFF) ^ 0x80) - 0x80" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_primitive_short_cast_emits_signed_narrowing() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public short truncate(int x) { return (short) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return ((int(x) & 0xFFFF) ^ 0x8000) - 0x8000" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_primitive_char_cast_emits_chr_with_mask() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public char fromInt(int x) { return (char) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return chr(int(x) & 0xFFFF)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_primitive_float_cast_emits_float_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public float narrow(double x) { return (float) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return float(x)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_primitive_double_cast_emits_float_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public double widen(int x) { return (double) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return float(x)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_reference_cast_emits_typing_cast_with_warning() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public MyType narrow(Object x) { return (MyType) x; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import cast" in result.source
    assert "return cast(MyType, x)  # cast: (MyType)" in result.source
    assert len(result.diagnostics.warnings) == 1
    assert result.diagnostics.warnings[0].reason == (
        "Java reference cast translated to typing.cast; verify runtime type"
    )
    assert_valid_python(result.source)


def test_numeric_cast_does_not_emit_typing_cast_import() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public int narrow(double x) { return (int) x; }
        }
        """,
    )
    assert "from typing import cast" not in result.source
    assert_valid_python(result.source)


def test_cast_expression_comment_is_suppressed_when_line_comments_are_disabled() -> None:
    cfg = CFG.model_copy(update={"emit_line_comments": False})
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public int narrow(double x) { return (int) x; }
        }
        """,
        cfg=cfg,
    )

    assert "return int(x)" in result.source
    assert "# cast:" not in result.source
    assert_valid_python(result.source)


def test_local_variable_cast_emits_trailing_comment() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public String name(Object x) {
                String name = (String) x;
                return name;
            }
        }
        """,
    )

    assert "name = cast(str, x)  # cast: (String)" in result.source
    assert_valid_python(result.source)


def test_condition_cast_comment_stays_on_condition_line() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public int choose(Object x) {
                if ((Integer) x > 0) {
                    return 1;
                }
                return 0;
            }
        }
        """,
    )

    assert "if cast(int, x) > 0:  # cast: (Integer)" in result.source
    assert "return 1  # cast:" not in result.source
    assert_valid_python(result.source)


def test_int_cast_of_char_parameter_emits_ord() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public int code(char c) { return (int) c; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return ord(c)" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_float_cast_of_char_parameter_emits_float_ord() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDemo {
            public double asDouble(char c) { return (double) c; }
        }
        """,
    )
    assert result.coverage == 1.0
    assert "return float(ord(c))" in result.source
    assert not result.diagnostics.warnings
    assert_valid_python(result.source)


def test_method_named_forecast_does_not_trigger_cast_import() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Weather {
            public String forecast(int days) { return "sunny"; }
        }
        """,
    )
    assert "from typing import cast" not in result.source
    assert_valid_python(result.source)


# ---------------------------------------------------------------------------
# Assignment-as-expression desugaring (#353)
# ---------------------------------------------------------------------------


def test_simple_assignment_in_null_check_becomes_walrus() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Drain {
            public void drain(java.util.Queue<String> q) {
                String item;
                while ((item = q.poll()) != null) {
                    process(item);
                }
            }
            private void process(String s) {}
        }
        """,
    )
    assert "(item := q.poll()) is not None" in result.source
    assert_valid_python(result.source)


def test_compound_assign_in_binary_condition_is_hoisted() -> None:
    result = translate_source_with_diagnostics(
        """
        public class FreqSketch {
            private int size;
            private int sampleSize;
            public void tryReset(boolean added) {
                if (added && (size += 1) == sampleSize) {
                    doReset();
                }
            }
            private void doReset() {}
        }
        """,
    )
    src = result.source
    assert "self.size += 1" in src
    assert "self.size == self.sample_size" in src
    assert_valid_python(src)


def test_prefix_update_in_binary_condition_is_hoisted() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Timer {
            private int steps;
            private int limit;
            public String nextBucket() {
                return ++steps < limit ? "a" : null;
            }
        }
        """,
    )
    src = result.source
    assert "self.steps += 1" in src
    assert '"a" if self.steps < self.limit else None' in src
    assert_valid_python(src)


def test_field_assignment_in_ternary_branch_is_hoisted() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Lazy {
            private Object cache;
            public Object get() {
                Object v = cache;
                return v != null ? v : (cache = compute());
            }
            private Object compute() { return new Object(); }
        }
        """,
    )
    src = result.source
    assert "self.cache = self.compute()" in src
    assert "v if v is not None else self.cache" in src
    assert_valid_python(src)


def test_local_var_assignment_in_not_operand_becomes_walrus() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Strip {
            public void offer(Object e, java.util.Queue<Object> buf) {
                boolean uncontended;
                if (!(uncontended = buf.offer(e))) {
                    retry(e);
                }
            }
            private void retry(Object e) {}
        }
        """,
    )
    src = result.source
    assert "uncontended := buf.offer(e)" in src
    assert "not " in src
    assert_valid_python(src)


def test_nested_assignment_in_assignment_rhs_is_hoisted() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Queue {
            private int size;
            public int insertNext() {
                int insertIndex = size += 1;
                return insertIndex;
            }
        }
        """,
    )
    src = result.source
    assert "self.size += 1" in src
    assert "insert_index = self.size" in src
    assert_valid_python(src)


def test_update_in_local_var_declaration_is_hoisted() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Agg {
            private int i;
            public int nextIndex() {
                int index = i++;
                return index;
            }
        }
        """,
    )
    src = result.source
    # post-increment hoisted; index gets the old value
    assert "self.i += 1" in src
    assert "index = " in src
    assert_valid_python(src)


def test_length_field_on_assignment_lhs_is_not_rewritten_to_len_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class ByteBuffer {
            private int length;

            public ByteBuffer(int n) {
                this.length = n;
            }
        }
        """,
    )
    src = result.source
    assert "self.length = n" in src
    assert "len(self) = " not in src
    assert_valid_python(src)


def test_compound_assign_in_method_argument_is_hoisted() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Iter {
            private int position;
            public String nextValue() {
                return get(position += 1);
            }
            private String get(int idx) { return ""; }
        }
        """,
    )
    src = result.source
    assert "self.position += 1" in src
    assert "self.get(self.position)" in src
    assert_valid_python(src)


def test_field_assignment_in_expression_lambda_is_promoted_to_helper() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Splitter {
            private String prefix;
            private java.util.function.Function<String,String> fn;
            public void process(java.util.Spliterator<String> src) {
                src.tryAdvance(elem -> this.prefix = fn.apply(elem));
            }
        }
        """,
    )
    src = result.source
    assert "self.prefix = self.fn.apply(elem)" in src
    assert_valid_python(src)
