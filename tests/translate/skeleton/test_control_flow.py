"""Skeleton translator tests — control flow and exception handling."""



from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file, parse_source
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.translate.skeleton.helpers import (
    CFG,
    FIXTURES,
    assert_module_executes,
    assert_valid_python,
    translate_source,
    translate_source_with_diagnostics,
)


def _malformed_for_diagnostics(result) -> list:
    return [
        item
        for item in result.diagnostics.unhandled
        if "malformed for statement" in item.reason
    ]


def test_classic_for_statement_translates_to_range_loop() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)


def test_for_statement_without_update_translates_to_while_loop() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.Enumeration;
        import java.util.List;
        import java.util.Map;

        public class Loops {
            public List<Object> names(Map<Object, Object> mappings) {
                List<Object> names = new ArrayList<>();
                for (Enumeration<?> en = mappings.keys(); en.hasMoreElements();) {
                    names.add(en.nextElement());
                }
                return names;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "while en.has_more_elements():" in result.source
    assert "names.append(en.next_element())" in result.source
    assert_valid_python(result.source)


def test_for_statement_with_iterator_and_no_update_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.Iterator;
        import java.util.List;
        import java.util.Set;

        public class Loops {
            public void consume(Set<Object> result) {
                for (Iterator<Object> it = result.iterator(); it.hasNext();) {
                    it.next();
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "while it.has_next():" in result.source
    assert "it.next()" in result.source
    assert_valid_python(result.source)


def test_for_statement_without_initializer_or_update_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Loops {
            public int countDown(int limit) {
                int seen = 0;
                for (; limit > 0;) {
                    seen += 1;
                    limit -= 1;
                }
                return seen;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "while limit > 0:" in result.source
    assert "limit -= 1" in result.source
    assert_valid_python(result.source)


def test_for_statement_without_condition_warns_and_uses_while_true() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Loops {
            public void spin() {
                for (;;) {
                    break;
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert "while True:" in result.source
    assert any(
        "for loop without condition lowered to while True" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_while_statement_translates_break_and_update() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_do_while_statement_translates_to_guarded_infinite_loop() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_try_catch_finally_and_throw_use_exception_map() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_multi_catch_exception_types_translate_to_tuple_handler() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_switch_statement_translates_returning_cases() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_switch_statement_merges_grouped_labels_and_ignores_label_comments() -> None:
    python_source, coverage = translate_source(
        """
        public class Switches {
            public int pick(int value) {
                switch (value) {
                    case 1:
                    // grouped with the next label
                    case 2:
                        return 3;
                    default:
                        return 0;
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if value in (1, 2):" in python_source
    assert "# grouped with the next label" in python_source
    assert "TODO(j2py): unsupported switch group line_comment" not in python_source
    assert "return 3" in python_source
    assert "else:" in python_source
    assert "return 0" in python_source
    assert_valid_python(python_source)





def test_switch_statement_merges_grouped_default_label() -> None:
    python_source, coverage = translate_source(
        """
        public class Switches {
            public int pick(int value) {
                switch (value) {
                    case 1:
                        return 1;
                    case 2:
                    default:
                        throw new IllegalArgumentException();
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if value == 1:" in python_source
    assert "else:" in python_source
    assert "raise ValueError()" in python_source
    assert "TODO(j2py): switch fall-through requires manual translation" not in python_source
    assert_valid_python(python_source)





def test_switch_statement_with_fallthrough_to_default_translates() -> None:
    result = translate_source_with_diagnostics(
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

    assert result.coverage == 1.0
    assert "TODO(j2py): switch fall-through requires manual translation" not in result.source
    assert "if value == 1:" in result.source
    assert "elif value not in (1):" in result.source
    assert_valid_python(result.source)


def test_switch_fallthrough_corpus_construct_reaches_full_coverage() -> None:
    parsed = parse_file(FIXTURES / "corpus" / "constructs" / "SwitchFallthrough.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "elif value == 3:" in result.source
    assert "if value in (3, 4, 5):" in result.source
    assert_valid_python(result.source)





def test_switch_expression_translates_arrow_rules_and_yield_blocks() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_if_statement_translates_single_branch() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_if_statement_translates_else_branch() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_if_statement_translates_chained_else_if() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_if_statement_translates_nested_branch() -> None:
    python_source, coverage = translate_source(
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
    assert_valid_python(python_source)





def test_if_statement_translates_instanceof_condition() -> None:
    python_source, coverage = translate_source(
        """
        public class Branch {
            public int supported(Object value) {
                if (value instanceof String) {
                    return 1;
                }
                return 0;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "if isinstance(value, str):" in python_source
    assert "unsupported if_statement" not in python_source
    assert_valid_python(python_source)





def test_try_with_resources_effectively_final_resource_translates() -> None:
    python_source, coverage = translate_source(
        """
        public class TryWithResourceVariable {
            public String read(Resource resource) {
                try (resource) {
                    return resource.read();
                }
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "with resource:" in python_source
    assert "return resource.read()" in python_source
    assert "malformed try-with-resources resource" not in python_source
    assert_valid_python(python_source)





def test_synchronized_this_in_static_method_emits_todo() -> None:
    python_source, coverage = translate_source(
        """
        public class SyncStatic {
            public static void guarded() {
                synchronized (this) {
                    run();
                }
            }
        }
        """,
    )

    assert coverage < 1.0
    assert "TODO(j2py): synchronized(this) in static context" in python_source
    assert "import threading" not in python_source
    assert "_j2py_lock" not in python_source





def test_nested_synchronized_this_does_not_initialize_outer_lock() -> None:
    python_source, coverage = translate_source(
        """
        public class Outer {
            static class Inner {
                public void guarded() {
                    synchronized (this) {
                        run();
                    }
                }
            }
        }
        """,
    )

    outer_block = python_source.split("    class Inner:", 1)[0]

    assert coverage == 1.0
    assert "self._j2py_lock" not in outer_block
    assert python_source.count("self._j2py_lock = threading.Lock()") == 1
    assert "with self._j2py_lock:" in python_source





def test_synchronized_non_this_lock_uses_j2py_monitor() -> None:
    parsed = parse_source(
        """
        public class SyncLock {
            private final Object monitor = new Object();

            public void guarded() {
                synchronized (monitor) {
                    run();
                }
            }
        }
        """,
    )
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert "with _j2py_monitor(self.monitor):" in result.source
    assert "from j2py_runtime import _j2py_monitor" in result.source
    assert any(
        "_j2py_monitor" in warning.reason
        for warning in result.diagnostics.warnings
    )
    assert_valid_python(result.source)


def test_synchronized_class_literal_uses_j2py_monitor() -> None:
    python_source, _ = translate_source(
        """
        public class Registry {
            public static void register() {
                synchronized (Registry.class) {
                    doRegister();
                }
            }
        }
        """,
    )

    assert "with _j2py_monitor(Registry):" in python_source
    assert "from j2py_runtime import _j2py_monitor" in python_source
    assert_valid_python(python_source)


def test_class_with_both_synchronized_this_and_object_emits_both_imports() -> None:
    # The non-this lock is a user-defined type (translates to a real, defined
    # class) so the emitted module is genuinely runnable — see assert_module_executes.
    python_source, _ = translate_source(
        """
        class WriteLock {}

        public class Dual {
            private final WriteLock writeLock = new WriteLock();

            public void onThis() {
                synchronized (this) { doA(); }
            }

            public void onObj() {
                synchronized (writeLock) { doB(); }
            }
        }
        """,
    )

    assert "with self._j2py_lock:" in python_source
    assert "with _j2py_monitor(self.write_lock):" in python_source
    assert "import threading" in python_source
    assert "from j2py_runtime import _j2py_monitor" in python_source
    assert_module_executes(python_source)


def test_synchronized_import_not_emitted_for_field_named_j2py_monitor() -> None:
    python_source, _ = translate_source(
        """
        public class Bad {
            private Object _j2py_monitor;
            public void set(Object o) { this._j2py_monitor = o; }
        }
        """,
    )

    assert "from j2py_runtime import _j2py_monitor" not in python_source
    assert_valid_python(python_source)


def test_var_local_and_enhanced_for_infer_types() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.ArrayList;
        import java.util.List;
        import java.util.Map;

        public class VarDemo {
            public List<String> demo(List<Map<String, Object>> data) {
                var results = new ArrayList<String>();
                for (var item : data) {
                    var name = (String) item.get("name");
                    results.add(name);
                }
                return results;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert ": var" not in python_source
    assert "results: list[str] = []" in python_source
    assert "name = cast(str, item.get(\"name\"))" in python_source
    assert "from typing import cast" in python_source
    assert_valid_python(python_source)


def test_var_cast_double_division_uses_true_division() -> None:
    python_source, coverage = translate_source(
        """
        import java.util.List;

        public class Average {
            public double average(List<Integer> numbers) {
                var sum = numbers.stream().mapToInt(Integer::intValue).sum();
                var average = numbers.isEmpty() ? 0.0 : (double) sum / numbers.size();
                return average;
            }
        }
        """,
    )

    assert coverage == 1.0
    assert "__j2py_todo__" not in python_source
    assert_valid_python(python_source)
