"""Skeleton translator tests — overload translation."""



from tests.translate.skeleton.helpers import (
    assert_module_executes,
    assert_valid_python,
    translate_source,
    translate_source_with_diagnostics,
)


def test_type_dispatch_overloads_emit_same_name_defs_behind_runtime_dispatcher() -> None:
    python_source, coverage = translate_source(
        """
        public class Over {
            public int get(int value) { return value; }
            public int get(String value) { return 1; }
        }
        """,
    )

    assert coverage == 1.0
    assert "from j2py_runtime import overloaded" in python_source
    assert python_source.count("@overloaded") == 2
    assert "def get(self, value: int) -> int:" in python_source
    assert (
        "def get(self, value: str) -> int:  # type: ignore[no-redef]  # noqa: F811"
    ) in python_source
    assert "NotImplementedError" not in python_source
    assert "from typing import overload" not in python_source
    assert_valid_python(python_source)


def test_static_overloads_emit_runtime_dispatcher_with_staticmethod_wrapping() -> None:
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
    assert "from j2py_runtime import overloaded" in python_source
    assert "from typing import overload" not in python_source
    assert python_source.count("@staticmethod\n    @overloaded") == 4
    assert "def get_instance(name: object) -> str:" in python_source
    assert (
        "def get_instance(object_name: str) -> str:  # type: ignore[no-redef]  # noqa: F811"
    ) in python_source
    assert (
        "def get_instance(domain_name: str, properties: dict[str, str]) "
        "-> str:  # type: ignore[no-redef]  # noqa: F811"
    ) in python_source
    assert 'return ObjectNames.get_instance("fallback")' in python_source
    assert "NotImplementedError" not in python_source
    assert_module_executes(python_source)


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
    assert 'name: str | None = None' in result.source
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
