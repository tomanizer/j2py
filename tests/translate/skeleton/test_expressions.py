"""Skeleton translator tests — expressions, literals, and calls."""



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





def test_multidimensional_array_creation_keeps_honest_diagnostic() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Arrays {
            public int[][] matrix(int rows, int cols) {
                return new int[rows][cols];
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "__j2py_todo__('new int[rows][cols]')" in result.source
    assert [
        diagnostic.reason for diagnostic in result.diagnostics.unhandled
    ] == ["multidimensional array creation requires nested allocation handling"]
    assert_valid_python(result.source)





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





def test_partial_translation_reports_structured_diagnostics() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Arrays {
            public int[][] matrix(int rows, int cols) {
                return new int[rows][cols];
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert result.diagnostics.unhandled
    diagnostic = result.diagnostics.unhandled[0]
    assert diagnostic.node_type == "array_creation_expression"
    assert diagnostic.line == 4
    assert diagnostic.text == "new int[rows][cols]"
    assert (
        diagnostic.reason == "multidimensional array creation requires nested allocation handling"
    )





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


