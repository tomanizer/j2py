"""Skeleton translator tests — overload translation."""

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
