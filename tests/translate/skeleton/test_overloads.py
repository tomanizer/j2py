"""Skeleton translator tests — overload translation."""



from tests.translate.skeleton.helpers import (
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
    assert [warning.reason for warning in result.diagnostics.warnings].count(
        "dropped Java cast; verify runtime type",
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



