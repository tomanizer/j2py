"""Skeleton translator tests — overload translation."""

from pathlib import Path

import pytest

from j2py.validate.checks import validate_source
from tests.translate.skeleton.helpers import (
    assert_module_executes,
    assert_valid_python,
    translate_source,
    translate_source_with_diagnostics,
)


def test_type_dispatch_overloads_emit_value_dispatcher() -> None:
    python_source, coverage = translate_source(
        """
        public class Over {
            public int get(int value) { return value; }
            public int get(String value) { return 1; }
        }
        """,
    )

    assert coverage == 1.0
    assert "from typing import overload" in python_source
    assert "from j2py_runtime import overloaded" not in python_source
    assert python_source.count("    @overload") == 2
    assert "def get(self, value: int) -> int:" in python_source
    assert "def get(self, value: str) -> int:" in python_source
    assert "def get(self, *args: object) -> int:" in python_source
    assert "if len(args) == 1 and isinstance(args[0], str):" in python_source
    assert (
        "if len(args) == 1 and isinstance(args[0], int) and not isinstance(args[0], bool):"
    ) in python_source
    assert "NotImplementedError" not in python_source
    assert_valid_python(python_source)


def test_value_dispatch_widens_int_arguments_to_float_overload() -> None:
    python_source, coverage = translate_source(
        """
        public class NumericDispatch {
            public String pick(double value) { return "float"; }
            public String pick(String value) { return "str"; }
            public String run() { return pick(1); }
        }
        """,
    )

    assert coverage == 1.0
    assert "isinstance(args[0], (int, float)) and not isinstance(args[0], bool)" in python_source
    namespace: dict[str, object] = {}
    exec(compile(python_source, "<translated>", "exec"), namespace)
    assert namespace["NumericDispatch"]().run() == "float"  # type: ignore[index,operator]


def test_static_value_dispatch_widens_int_arguments_to_float_overload() -> None:
    python_source, coverage = translate_source(
        """
        public class NumericDispatch {
            public static String pick(double value) { return "float"; }
            public static String pick(String value) { return "str"; }
            public static String run() { return pick(1); }
        }
        """,
    )

    assert coverage == 1.0
    namespace: dict[str, object] = {}
    exec(compile(python_source, "<translated>", "exec"), namespace)
    assert namespace["NumericDispatch"].run() == "float"  # type: ignore[index,union-attr]


def test_value_dispatch_prefers_int_over_float_for_integer_arguments() -> None:
    python_source, coverage = translate_source(
        """
        public class NumericDispatch {
            public String pick(int value) { return "int"; }
            public String pick(double value) { return "float"; }
            public String run() { return pick(1); }
        }
        """,
    )

    assert coverage == 1.0
    assert python_source.index("isinstance(args[0], int)") < python_source.index(
        "isinstance(args[0], (int, float))",
    )
    namespace: dict[str, object] = {}
    exec(compile(python_source, "<translated>", "exec"), namespace)
    assert namespace["NumericDispatch"]().run() == "int"  # type: ignore[index,operator]


def test_static_overloads_emit_value_dispatcher_with_staticmethod_wrapping() -> None:
    python_source, coverage = translate_source(
        """
        public class ObjectNames {
            public static String getInstance(Object name) {
                return getInstance("fallback");
            }

            public static String getInstance(String objectName) {
                return objectName;
            }

            public static String getInstance(String domainName, String key, String value) {
                return domainName + key + value;
            }

            public static String getInstance(
                    String domainName, Hashtable<String, String> properties) {
                return domainName;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from typing import overload" in python_source
    assert "from j2py_runtime import overloaded" not in python_source
    assert python_source.count("@staticmethod\n    @overload") == 4
    assert "def get_instance(name: object) -> str:" in python_source
    assert "def get_instance(object_name: str) -> str:" in python_source
    assert (
        "def get_instance(domain_name: str, properties: dict[str, str]) -> str:"
    ) in python_source
    assert "def get_instance(*args: object) -> str:" in python_source
    assert "if len(args) == 1 and isinstance(args[0], str):" in python_source
    assert (
        "if len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], dict):"
    ) in python_source
    assert 'return ObjectNames.get_instance("fallback")' in python_source
    assert "NotImplementedError" not in python_source
    assert_module_executes(python_source)


def test_object_name_static_overloads_emit_typing_dispatcher() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.Hashtable;
        import javax.management.MalformedObjectNameException;
        import javax.management.ObjectName;

        public class ObjectNameManagerProbe {
            public static ObjectName getInstance(Object name) throws MalformedObjectNameException {
                if (name instanceof ObjectName objectName) {
                    return objectName;
                }
                if (name instanceof String text) {
                    return getInstance(text);
                }
                throw new MalformedObjectNameException();
            }

            public static ObjectName getInstance(String objectName)
                    throws MalformedObjectNameException {
                return ObjectName.getInstance(objectName);
            }

            public static ObjectName getInstance(String domainName, String key, String value)
                    throws MalformedObjectNameException {
                return ObjectName.getInstance(domainName, key, value);
            }

            public static ObjectName getInstance(
                    String domainName, Hashtable<String, String> properties)
                    throws MalformedObjectNameException {
                return ObjectName.getInstance(domainName, properties);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from j2py_runtime import ObjectName" in result.source
    assert "from j2py_runtime import MalformedObjectNameException" in result.source
    assert "from typing import overload" in result.source
    assert "from j2py_runtime import overloaded" not in result.source
    assert "from javax." not in result.source
    assert result.source.count("    @staticmethod\n    @overload") == 4
    assert "def get_instance(*args: object) -> ObjectName:" in result.source
    assert "if len(args) == 1 and isinstance(args[0], str):" in result.source
    assert "if len(args) == 1:" in result.source
    assert (
        "if len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], dict):"
    ) in result.source
    assert (
        "if len(args) == 3 and isinstance(args[0], str) "
        "and isinstance(args[1], str) and isinstance(args[2], str):"
    ) in result.source
    assert "return ObjectNameManagerProbe.get_instance(text)" in result.source
    assert "return ObjectName.get_instance(object_name)" in result.source
    assert "NotImplementedError" not in result.source
    assert_valid_python(result.source)


def test_generic_bounded_return_typevars_are_preserved_for_overload_groups() -> None:
    result = translate_source_with_diagnostics(
        """
        public class GenericOverloads {
            public static <A extends Appendable, T> A join(A out, Iterable<T> values) {
                return out;
            }

            public static <A extends Appendable, T> A join(A out, T value) {
                return out;
            }

            public static <B extends Closeable, T> B collect(B target, Iterable<T> values) {
                return target;
            }

            public static <B extends Closeable, T> B collect(B target, T value) {
                return target;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import Iterable, Protocol, TypeVar, overload" in result.source
    assert "class Appendable(Protocol):" in result.source
    assert "class Closeable(Protocol):" in result.source
    assert 'A = TypeVar("A", bound=Appendable)' in result.source
    assert 'B = TypeVar("B", bound=Closeable)' in result.source
    assert 'T = TypeVar("T")' in result.source
    assert "def join(out: A, values: Iterable[T]) -> A: ..." in result.source
    assert "def join(out: A, value: T) -> A: ..." in result.source
    assert "def join(*args: object) -> object:" in result.source
    assert "def collect(target: B, values: Iterable[T]) -> B: ..." in result.source
    assert "def collect(target: B, value: T) -> B: ..." in result.source
    assert "def collect(*args: object) -> object:" in result.source
    assert "overloaded method join requires manual dispatch" not in {
        item.reason for item in result.diagnostics.unhandled
    }
    assert "overloaded method collect requires manual dispatch" not in {
        item.reason for item in result.diagnostics.unhandled
    }
    validation = validate_source(result.source, Path("GenericOverloads.py"))
    assert validation.ok, validation.ruff_errors + validation.mypy_errors


def test_static_erasure_collisions_keep_manual_dispatch_fallback() -> None:
    python_source, coverage = translate_source(
        """
        public class StaticOver {
            public static int width(int value) { return value; }
            public static int width(long value) { return 1; }
        }
        """,
    )

    assert coverage < 1.0
    assert "@overload" in python_source
    assert "@overloaded" not in python_source
    assert "def width(*args: object) -> object:" in python_source
    assert "TODO(j2py): overloaded method width requires manual dispatch" in python_source
    assert_valid_python(python_source)


def test_static_forwarding_overload_merges_defaults() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Ranges {
            public static Range of(String start, String end) {
                return of(start, end, null);
            }

            public static Range of(String start, String end, Comparator comparator) {
                return new Range(start, end, comparator);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import overload" in result.source
    assert "from j2py_runtime import overloaded" not in result.source
    assert "def of(start: str, end: str, comparator: Comparator = None) -> Range:" in result.source
    assert "return Range(start, end, comparator)" in result.source
    assert_valid_python(result.source)


def test_same_arity_boxed_wrapper_forwarding_merges_to_implementation() -> None:
    result = translate_source_with_diagnostics(
        """
        public class DoubleRange {
            public static DoubleRange of(double fromInclusive, double toInclusive) {
                return of(Double.valueOf(fromInclusive), Double.valueOf(toInclusive));
            }

            public static DoubleRange of(Double fromInclusive, Double toInclusive) {
                return new DoubleRange(fromInclusive, toInclusive);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import overload" in result.source
    assert "from j2py_runtime import overloaded" not in result.source
    assert result.source.count("def of(") == 3
    assert "def of(from_inclusive: float, to_inclusive: float) -> DoubleRange:" in result.source
    assert "return DoubleRange(from_inclusive, to_inclusive)" in result.source
    assert "NotImplementedError" not in result.source
    assert_valid_python(result.source)


def test_static_annotated_varargs_overloads_dispatch_after_parameter_recovery() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Scripts {
            public static Object create(String scriptSource) {
                return create(scriptSource, null, null);
            }

            public static Object create(
                    String scriptSource, Class<?> @Nullable ... scriptInterfaces) {
                return create(scriptSource, scriptInterfaces, ClassUtils.getDefaultClassLoader());
            }

            public static Object create(
                    String scriptSource, Class<?> @Nullable [] scriptInterfaces,
                    @Nullable ClassLoader classLoader) {
                return evaluate(scriptSource, scriptInterfaces, classLoader);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from j2py_runtime import overloaded" in result.source
    assert result.source.count("@staticmethod\n    @overloaded") == 3
    assert "def create(script_source: str) -> object:" in result.source
    assert (
        "def create(script_source: str, *script_interfaces: type[Any]) "
        "-> object:  # type: ignore[no-redef]  # noqa: F811"
    ) in result.source
    assert (
        "def create(script_source: str, script_interfaces: list[type[Any]], "
        "class_loader: ClassLoader) -> object:  # type: ignore[no-redef]  # noqa: F811"
    ) in result.source
    assert "return Scripts.create(script_source, None, None)" in result.source
    assert (
        "return Scripts.create(script_source, script_interfaces, "
        "class_utils.get_default_class_loader())"
    ) in result.source
    assert_valid_python(result.source)


def test_erasure_collided_overloads_keep_manual_dispatch_fallback() -> None:
    """int and long both erase to Python int; runtime dispatch cannot tell them apart."""
    python_source, coverage = translate_source(
        """
        public class Over {
            public int width(int value) { return value; }
            public int width(long value) { return 1; }
        }
        """,
    )

    assert coverage < 1.0
    assert "@overload" in python_source
    assert "@overloaded" not in python_source
    assert (
        "TODO(j2py): overloaded method width requires manual dispatch for signatures: "
        "width(value: int); width(value: int)"
    ) in python_source
    assert "def width(self, *args: object) -> object:" in python_source
    assert 'raise NotImplementedError("j2py overload dispatch required")' in python_source
    assert_valid_python(python_source)


def test_append_char_string_overload_uses_value_dispatcher() -> None:
    result = translate_source_with_diagnostics(
        """
        class StringBuilder {
            public void addChar(char value) {
            }

            public void addString(Object value) {
            }
        }

        public class OverloadDispatchProbe {
            public OverloadDispatchProbe append(StringBuilder builder, char value) {
                builder.addChar(value);
                return this;
            }

            public OverloadDispatchProbe append(StringBuilder builder, String value) {
                builder.addString(value);
                return this;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import Self, overload" in result.source
    assert "from j2py_runtime import overloaded" not in result.source
    assert result.source.count("    @overload") == 2
    assert "def append(self, builder: StringBuilder, value: str) -> Self:" in result.source
    assert "def append(self, *args: object) -> Self:" in result.source
    assert (
        "if len(args) == 2 and isinstance(args[1], str) and len(args[1]) == 1:"
    ) in result.source
    assert "if len(args) == 2 and isinstance(args[1], str):" in result.source
    assert "builder.add_char(value)" in result.source
    assert "builder.add_string(value)" in result.source
    assert "overloaded method append requires manual dispatch" not in result.source
    assert "NotImplementedError" not in result.source
    assert_valid_python(result.source)


def test_collection_shape_overloads_use_value_dispatcher() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.List;
        import java.util.Map;
        import java.util.Set;

        public class CollectionDispatch {
            public static String describe(List<String> values) {
                return "list";
            }

            public static String describe(Set<String> values) {
                return "set";
            }

            public static String describe(Map<String, String> values) {
                return "map";
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "from typing import overload" in result.source
    assert "from j2py_runtime import overloaded" not in result.source
    assert "def describe(*args: object) -> str:" in result.source
    assert "if len(args) == 1 and isinstance(args[0], list):" in result.source
    assert "if len(args) == 1 and isinstance(args[0], set):" in result.source
    assert "if len(args) == 1 and isinstance(args[0], dict):" in result.source
    assert "NotImplementedError" not in result.source
    assert_valid_python(result.source)


def test_generic_collection_erasure_collision_keeps_manual_dispatch_fallback() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.List;

        public class GenericCollision {
            public Object first(List<String> values) { return values.get(0); }
            public Object first(List<Integer> values) { return values.get(0) + 1; }
        }
        """,
    )

    assert coverage < 1.0
    assert "@overload" in python_source
    assert "@overloaded" not in python_source
    assert "TODO(j2py): overloaded method first requires manual dispatch" in python_source
    assert 'raise NotImplementedError("j2py overload dispatch required")' in python_source
    assert_valid_python(python_source)


def test_overload_default_expression_diagnostics_are_preserved() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CastDefaults {
            private String name;

            public CastDefaults() {
                this((String) "default");
            }

            public CastDefaults(String name) {
                this.name = name;
            }

            public String label() {
                return label((String) "default");
            }

            public String label(String value) {
                return value;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "name: str | None = None" in result.source
    assert 'separator: str = "-"' not in result.source
    assert "from typing import cast" in result.source
    assert [warning.reason for warning in result.diagnostics.warnings].count(
        "Java reference cast translated to typing.cast; verify runtime type",
    ) == 2
    assert_valid_python(result.source)


def test_overload_dispatch_trailing_comment_still_counts_as_terminal() -> None:
    python_source, coverage = translate_source(
        """
        public class Dispatch {
            public String get() {
                return "default";
                // keep this comment with the branch
            }

            public String get(String value) {
                return value;
                // keep this comment with the branch
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "# keep this comment with the branch" in python_source
    assert "return None" not in python_source
    assert_valid_python(python_source)


def test_merged_overload_block_lambda_emits_helper_before_use() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_erased_numeric_comparison_overloads_collapse_to_single_method() -> None:
    # The Java compare(byte/int/long) family erases to one Python signature
    # compare(x: int, y: int). The narrow overload returns the difference form
    # (x - y) and the wide ones the explicit sign form; both honour the Comparator
    # sign contract and, once the integral types erase to a single unbounded Python
    # int, the difference form cannot overflow — so the group is provably equivalent
    # and collapses to one method instead of an impossible runtime dispatch (#379).
    python_source, coverage = translate_source(
        """
        public class Cmp {
            public static int compare(byte x, byte y) {
                return x - y;
            }
            public static int compare(int x, int y) {
                if (x == y) {
                    return 0;
                }
                return x < y ? -1 : 1;
            }
            public static int compare(long x, long y) {
                if (x == y) {
                    return 0;
                }
                return x < y ? -1 : 1;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert python_source.count("def compare(") == 1
    assert "TODO(j2py): overloaded method compare" not in python_source
    assert "NotImplementedError" not in python_source
    # The explicit sign form is kept as the representative — value-identical to Java
    # for the wide overloads, sign-correct for the narrow one.
    assert "return -1 if x < y else 1" in python_source
    assert_module_executes(python_source)

    # Runtime behaviour: the collapsed method honours the comparison sign contract,
    # including across the full byte range (the narrow overload's domain).
    namespace: dict[str, object] = {}
    exec(compile(python_source, "<cmp>", "exec"), namespace)
    cmp = namespace["Cmp"]
    assert cmp.compare(5, 2) > 0
    assert cmp.compare(2, 5) < 0
    assert cmp.compare(3, 3) == 0
    assert cmp.compare(-128, 127) < 0


def test_fixed_arity_beats_varargs_in_value_dispatcher() -> None:
    python_source, coverage = translate_source(
        """
        public class Stats {
            public static int max(int a, int b, int c) {
                return a > b ? (a > c ? a : c) : (b > c ? b : c);
            }

            public static int max(int... values) {
                return values[0];
            }

            public static int runThree() {
                return max(1, 2, 3);
            }

            public static int runVarargs() {
                return max(4, 5);
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "from typing import overload" in python_source
    assert "from j2py_runtime import overloaded" not in python_source
    assert "def max_(a: int, b: int, c: int) -> int:" in python_source
    assert "def max_(*values: int) -> int:" in python_source
    assert "def max_(*args: object) -> int:" in python_source
    assert (
        "if len(args) == 3 and isinstance(args[0], int) and not isinstance(args[0], bool)"
    ) in python_source
    assert "if len(args) >= 0 and all(isinstance(value, int)" in python_source
    assert python_source.index("len(args) == 3") < python_source.index("len(args) >= 0")
    assert "NotImplementedError" not in python_source
    assert_valid_python(python_source)
    namespace: dict[str, object] = {}
    exec(compile(python_source, "<stats>", "exec"), namespace)
    stats = namespace["Stats"]
    assert stats.run_three() == 3  # type: ignore[attr-defined]
    assert stats.run_varargs() == 4  # type: ignore[attr-defined]


def test_varargs_erasure_collision_keeps_manual_dispatch_fallback() -> None:
    python_source, coverage = translate_source(
        """
        public class Unsafe {
            public static int pick(int... values) {
                return 1;
            }

            public static int pick(long... values) {
                return 2;
            }
        }
        """,
    )

    assert coverage < 1.0
    assert "TODO(j2py): overloaded method pick requires manual dispatch" in python_source
    assert_valid_python(python_source)


def test_differing_non_comparison_bodies_do_not_collapse() -> None:
    # Guard: same erased signature but genuinely different (non-comparison) bodies must
    # still fall back to a manual-dispatch TODO — the comparison collapse must not
    # over-merge unrelated numeric-width overloads.
    python_source, coverage = translate_source(
        """
        public class Widths {
            public static int pick(int value) { return value; }
            public static int pick(long value) { return 1; }
        }
        """,
    )

    # The manual-dispatch fallback intentionally leaves the group uncovered (< 1.0).
    assert coverage < 1.0
    assert "TODO(j2py): overloaded method pick requires manual dispatch" in python_source
    assert_valid_python(python_source)


def test_comparison_collapse_tolerates_comments_braceless_if_and_parens() -> None:
    # Robustness (review feedback on #379): the comparison-form recogniser must see through
    # comment nodes, a braceless `if` consequence, and parenthesized expressions — these are
    # all the same two sign-contract shapes, just spelled differently.
    python_source, coverage = translate_source(
        """
        public class Cmp {
            public static int compare(byte x, byte y) {
                // narrow overload returns the difference form
                return (x - y);
            }
            public static int compare(int x, int y) {
                if (x == y) return 0;
                return (x < y) ? -1 : 1;
            }
            public static int compare(long x, long y) {
                if (x == y) {
                    return 0;
                }
                return x < y ? -1 : 1;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert python_source.count("def compare(") == 1
    assert "TODO(j2py): overloaded method compare" not in python_source
    assert "NotImplementedError" not in python_source
    assert_module_executes(python_source)
    namespace: dict[str, object] = {}
    exec(compile(python_source, "<cmp>", "exec"), namespace)
    cmp = namespace["Cmp"]
    assert cmp.compare(5, 2) > 0
    assert cmp.compare(2, 5) < 0
    assert cmp.compare(3, 3) == 0


@pytest.mark.parametrize(
    ("fixture_name", "source", "expected_snippets"),
    [
        (
            "boxed_unboxed_char",
            """
            public class CharUtils {
                public static int toIntValue(char ch) { return ch; }
                public static int toIntValue(Character ch, int defaultValue) {
                    return defaultValue;
                }
            }
            """,
            (
                "def to_int_value(ch: str) -> int:",
                "def to_int_value(ch: str, default_value: int) -> int:",
                "isinstance(args[0], str) and len(args[0]) == 1",
            ),
        ),
        (
            "fluent_builder_append",
            """
            public class DiffBuilder {
                public DiffBuilder append(String fieldName, boolean value) {
                    this.flag = value;
                    return this;
                }
                public DiffBuilder append(String fieldName, int value) {
                    this.count = value;
                    return this;
                }
                public DiffBuilder append(String fieldName, Object value) {
                    this.obj = value;
                    return this;
                }
            }
            """,
            (
                "def append(self, field_name: str, value: bool)",
                "def append(self, field_name: str, value: int)",
                "def append(self, *args: object)",
            ),
        ),
        (
            "fixed_arity_vs_varargs_numeric",
            """
            public class IEEE754rUtils {
                public static int max_(int a, int b, int c) { return a; }
                public static int max_(int... values) { return values[0]; }
            }
            """,
            (
                "def max_(a: int, b: int, c: int) -> int:",
                "def max_(*values: int) -> int:",
                "len(args) == 3",
            ),
        ),
        (
            "identical_fluent_builder_merge",
            """
            public class DiffBuilder {
                public DiffBuilder append(String fieldName, boolean value) { return this; }
                public DiffBuilder append(String fieldName, int value) { return this; }
            }
            """,
            ("def append(self, field_name: str, value: bool | int)",),
        ),
    ],
    ids=[
        "boxed_unboxed_char",
        "fluent_builder_append",
        "fixed_arity_vs_varargs_numeric",
        "identical_fluent_builder_merge",
    ],
)
def test_issue_390_overload_families_avoid_manual_dispatch(
    fixture_name: str,
    source: str,
    expected_snippets: tuple[str, ...],
) -> None:
    del fixture_name
    result = translate_source_with_diagnostics(source)

    assert result.coverage == 1.0
    assert "requires manual dispatch" not in result.source
    assert "NotImplementedError" not in result.source
    for snippet in expected_snippets:
        assert snippet in result.source
    assert_valid_python(result.source)


def test_static_instance_collision_split_emits_both_members() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Circuit {
            public static boolean isOpen(Circuit breaker) {
                return breaker.isOpen();
            }

            public boolean isOpen() {
                return true;
            }

            public static boolean runStatic(Circuit breaker) {
                return isOpen(breaker);
            }

            public boolean runInstance() {
                return isOpen();
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "requires manual dispatch" not in result.source
    assert "static/instance overload split" in result.source
    assert "def is_open_static(breaker: Circuit) -> bool:" in result.source
    assert "def is_open(self) -> bool:" in result.source
    assert "Circuit.is_open_static(breaker)" in result.source
    assert "return self.is_open()" in result.source
    assert_valid_python(result.source)
    assert_module_executes(result.source)
    namespace: dict[str, object] = {}
    exec(compile(result.source, "<circuit>", "exec"), namespace)
    circuit = namespace["Circuit"]
    breaker = circuit()  # type: ignore[operator]
    assert circuit.run_static(breaker) is True  # type: ignore[attr-defined]
    assert breaker.run_instance() is True  # type: ignore[attr-defined]


def test_static_instance_collision_subclass_routes_inherited_static_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Base {
            public static boolean isOpen(Base breaker) {
                return true;
            }

            public boolean isOpen() {
                return false;
            }
        }

        public class Child extends Base {
            public static boolean run(Base breaker) {
                return isOpen(breaker);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return Base.is_open_static(breaker)" in result.source
    assert_valid_python(result.source)
    namespace: dict[str, object] = {}
    exec(compile(result.source, "<child>", "exec"), namespace)
    base = namespace["Base"]
    child = namespace["Child"]
    breaker = base()
    assert child.run(breaker) is True  # type: ignore[attr-defined]


def test_static_instance_collision_grandchild_routes_inherited_static_call() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Base {
            public static boolean isOpen(Base breaker) {
                return true;
            }

            public boolean isOpen() {
                return false;
            }
        }

        public class Mid extends Base {
        }

        public class Child extends Mid {
            public static boolean run(Base breaker) {
                return isOpen(breaker);
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return Base.is_open_static(breaker)" in result.source
    assert_valid_python(result.source)


def test_static_instance_collision_preserves_instance_first_declaration_order() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Circuit {
            public boolean isOpen() {
                return true;
            }

            public static boolean isOpen(Circuit breaker) {
                return breaker.isOpen();
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert result.source.index("def is_open(self)") < result.source.index(
        "def is_open_static(breaker: Circuit)",
    )
    assert "requires manual dispatch" not in result.source
    assert_valid_python(result.source)


def test_static_instance_collision_renames_multi_static_group() -> None:
    result = translate_source_with_diagnostics(
        """
        public class T {
            public static int pick(int value) {
                return value;
            }

            public static int pick(String value) {
                return 1;
            }

            public int pick() {
                return 0;
            }

            public static int runInt() {
                return pick(2);
            }

            public int runInstance() {
                return pick();
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "def pick_static(*args: object)" in result.source
    assert "def pick(self) -> int:" in result.source
    assert "return T.pick_static(2)" in result.source
    assert "return self.pick()" in result.source
    assert "requires manual dispatch" not in result.source
    assert_valid_python(result.source)


def test_char_utils_three_way_overloads_keep_review_stubs_with_value_dispatch() -> None:
    result = translate_source_with_diagnostics(
        """
        public class CharUtils {
            public static int toIntValue(char ch, int defaultValue) {
                return defaultValue;
            }

            public static int toIntValue(Character ch) {
                return ch;
            }

            public static int toIntValue(Character ch, int defaultValue) {
                return defaultValue;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert result.source.count("@overload") == 3
    assert "def to_int_value(*args: object)" in result.source
    assert "len(args) == 1" in result.source
    assert "len(args) == 2" in result.source
    assert "@overloaded" not in result.source
    assert "requires manual dispatch" not in result.source
    assert_valid_python(result.source)
    namespace: dict[str, object] = {}
    exec(compile(result.source, "<char>", "exec"), namespace)
    char_utils = namespace["CharUtils"]
    assert char_utils.to_int_value("a") == "a"  # type: ignore[attr-defined]
    assert char_utils.to_int_value("b", 9) == 9  # type: ignore[attr-defined]


def test_static_instance_collision_zero_arg_static_call_skips_renamed_static() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Circuit {
            public static boolean isOpen(Circuit breaker) {
                return breaker.isOpen();
            }

            public boolean isOpen() {
                return true;
            }

            public static boolean run() {
                return isOpen();
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return is_open()" in result.source
    assert "is_open_static()" not in result.source
    assert_valid_python(result.source)


def test_static_instance_collision_zero_arg_static_routes_to_renamed_static() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Widget {
            public static boolean isReady() {
                return true;
            }

            public boolean isReady(int code) {
                return code > 0;
            }

            public static boolean run() {
                return isReady();
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "return Widget.is_ready_static()" in result.source
    assert "self.is_ready()" not in result.source
    assert_valid_python(result.source)
    namespace: dict[str, object] = {}
    exec(compile(result.source, "<widget>", "exec"), namespace)
    widget = namespace["Widget"]
    assert widget.run() is True  # type: ignore[attr-defined]


def test_static_instance_collision_module_index_merges_parent_from_other_unit() -> None:
    from j2py.analyze.symbols import extract_symbols
    from j2py.config.loader import ConfigLoader
    from j2py.parse.java_ast import parse_source
    from j2py.translate.class_members import (
        collect_file_class_declarations,
        collect_file_class_static_instance_aliases,
        collect_file_class_static_methods,
        merge_class_declaration_indexes,
        merge_class_static_instance_alias_indexes,
        merge_class_static_method_indexes,
    )
    from j2py.translate.skeleton import translate_skeleton_with_diagnostics

    cfg = ConfigLoader().add_defaults().build()
    base_parsed = parse_source(
        """
        public class Base {
            public static boolean isOpen(Base breaker) {
                return true;
            }

            public boolean isOpen() {
                return false;
            }
        }
        """,
    )
    child_parsed = parse_source(
        """
        public class Child extends Base {
            public static boolean run(Base breaker) {
                return isOpen(breaker);
            }
        }
        """,
    )
    module_methods = merge_class_static_method_indexes(
        collect_file_class_static_methods(base_parsed.root, cfg),
        collect_file_class_static_methods(child_parsed.root, cfg),
    )
    module_aliases = merge_class_static_instance_alias_indexes(
        collect_file_class_static_instance_aliases(base_parsed.root, cfg),
        collect_file_class_static_instance_aliases(child_parsed.root, cfg),
    )
    module_declarations = merge_class_declaration_indexes(
        collect_file_class_declarations(base_parsed.root),
        collect_file_class_declarations(child_parsed.root),
    )
    result = translate_skeleton_with_diagnostics(
        child_parsed,
        extract_symbols(child_parsed),
        cfg,
        module_class_static_methods=module_methods,
        module_class_static_instance_aliases=module_aliases,
        module_class_declarations=module_declarations,
    )

    assert result.coverage == 1.0
    assert "return Base.is_open_static(breaker)" in result.source
    assert "requires manual dispatch" not in result.source
    assert_valid_python(result.source)
