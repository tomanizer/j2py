"""Skeleton translator tests — fields, enums, and type declarations."""



from tests.translate.skeleton.helpers import (
    assert_valid_python,
    translate_source,
    translate_source_with_diagnostics,
)


def test_field_without_constructor_assignment_uses_java_default() -> None:
    python_source, coverage = translate_source("public class FieldOnly { private int count; }")

    assert coverage == 1.0
    assert "self.count: int = 0" in python_source
    assert_valid_python(python_source)





def test_uninitialized_field_defaults_use_java_semantics() -> None:
    python_source, coverage = translate_source(
        """
        public class Defaults {
            private int count;
            private long total;
            private double ratio;
            private boolean enabled;
            private char marker;
            private String name;
            private int[] values;
            private static boolean ready;
        }
        """,
    )

    assert coverage == 1.0
    assert "ready: bool = False" in python_source
    assert "self.count: int = 0" in python_source
    assert "self.total: int = 0" in python_source
    assert "self.ratio: float = 0.0" in python_source
    assert "self.enabled: bool = False" in python_source
    assert 'self.marker: str = "\\0"' in python_source
    assert "self.name: str | None = None" in python_source
    assert "self.values: list[int] | None = None" in python_source
    assert "TODO(j2py): verify default value" not in python_source
    assert_valid_python(python_source)





def test_instance_field_initializer_can_reference_another_field() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_anonymous_class_method_can_emit_nested_block_lambda_helper() -> None:
    result = translate_source_with_diagnostics(
        """
        public class AnonymousHelpers {
            interface Maker {
                Runnable make(String prefix);
            }

            public Maker maker() {
                return new Maker() {
                    @Override
                    public Runnable make(String prefix) {
                        return () -> {
                            System.out.println(prefix);
                        };
                    }
                };
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "class _J2pyAnonymous1(Maker):" in result.source
    assert "def make(self, prefix: str) -> Runnable:" in result.source
    assert "def _j2py_lambda_1()" in result.source
    assert "print(prefix)" in result.source
    assert "return _j2py_lambda_1" in result.source
    assert result.source.index("def _j2py_lambda_1(") < result.source.index(
        "return _j2py_lambda_1",
    )
    assert_valid_python(result.source)





def test_enum_direct_declarations_do_not_capture_nested_type_members() -> None:
    result = translate_source_with_diagnostics(
        """
        public enum Outer {
            ONE("outer");

            private final String outerName;

            Outer(String outerName) {
                this.outerName = outerName;
            }

            public String label() {
                return outerName;
            }

            static class Nested {
                private final String nestedName;

                Nested(String nestedName) {
                    this.nestedName = nestedName;
                }

                public String label() {
                    return nestedName;
                }
            }
        }
        """,
    )

    assert "outer_name: str" in result.source
    assert "self.outer_name = outer_name" in result.source
    assert "return self.outer_name" in result.source
    assert "nested_name: str" not in result.source
    assert "self.nested_name" not in result.source
    assert_valid_python(result.source)





def test_enum_interface_names_skip_generic_type_arguments() -> None:
    result = translate_source_with_diagnostics(
        """
        public enum Mode implements Comparable<Mode>, Labelled {
            FAST;
        }
        """,
    )

    assert "# implements Comparable, Labelled" in result.source
    assert "# implements Comparable, Mode, Labelled" not in result.source
    assert_valid_python(result.source)





def test_super_constructor_invocation_and_base_class_translate() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_block_lambda_in_field_initializer_does_not_emit_undefined_helper() -> None:
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)





def test_grouping_by_in_field_initializer_does_not_emit_undefined_helper() -> None:
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)





def test_interface_declaration_translates_to_protocol() -> None:
    result = translate_source_with_diagnostics(
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
    assert_valid_python(result.source)





def test_annotation_type_declaration_emits_valid_placeholder() -> None:
    result = translate_source_with_diagnostics(
        """
        public @interface Marker {
        }
        """,
    )

    assert result.coverage == 0.0
    assert "class Marker:" in result.source
    assert "TODO(j2py): unsupported annotation type declaration" in result.source
    assert result.diagnostics.unhandled[0].node_type == "annotation_type_declaration"
    assert_valid_python(result.source)

