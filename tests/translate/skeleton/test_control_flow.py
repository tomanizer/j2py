"""Skeleton translator tests — control flow and exception handling."""

import pytest

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
        item for item in result.diagnostics.unhandled if "malformed for statement" in item.reason
    ]


def _load_translated_class(source: str, class_name: str):
    namespace: dict[str, object] = {}
    exec(compile(source, "<translated>", "exec"), namespace)
    return namespace[class_name]


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


def test_for_statement_multiple_declarator_initializers_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Loops {
            public int sumPair(int limit) {
                int total = 0;
                for (int left = 0, right = limit; left < right; left++, right--) {
                    total += left + right;
                }
                return total;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "left = 0" in result.source
    assert "right = limit" in result.source
    assert "while left < right:" in result.source
    assert "left += 1" in result.source
    assert "right -= 1" in result.source
    assert_valid_python(result.source)
    loops = _load_translated_class(result.source, "Loops")
    assert loops().sum_pair(4) == 8  # type: ignore[attr-defined,operator]


def test_for_statement_multiple_update_expressions_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Loops {
            public int walk(int limit) {
                int i = 0;
                int j = limit;
                for (; i < j; i++, j--) {
                    i += 0;
                }
                return i;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "while i < j:" in result.source
    assert "i += 1" in result.source
    assert "j -= 1" in result.source
    assert_valid_python(result.source)


def test_for_statement_bidirectional_index_pattern_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Loops {
            public boolean meetInMiddle(int len2) {
                for (int i = 1, j = len2 - 1; i <= j; i++, j--) {
                    if (i == j) {
                        return true;
                    }
                }
                return false;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "i = 1" in result.source
    assert "j = len2 - 1" in result.source
    assert "while i <= j:" in result.source
    assert "i += 1" in result.source
    assert "j -= 1" in result.source
    assert_valid_python(result.source)
    loops = _load_translated_class(result.source, "Loops")
    assert loops().meet_in_middle(2) is True  # type: ignore[attr-defined,operator]


def test_for_statement_multi_declarator_single_update_uses_while_not_range() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Loops {
            public int totalUp(int n) {
                int total = 0;
                for (int i = 0, j = 10; i < n; i++) {
                    total += i + j;
                }
                return total;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "for i in range(" not in result.source
    assert "i = 0" in result.source
    assert "j = 10" in result.source
    assert "while i < n:" in result.source
    assert "i += 1" in result.source
    assert_valid_python(result.source)
    loops = _load_translated_class(result.source, "Loops")
    assert loops().total_up(3) == 33  # type: ignore[attr-defined,operator]


def test_for_statement_expression_initializer_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        import java.util.ArrayList;
        import java.util.List;

        public class Loops {
            public int drain(List<String> values) {
                int seen = 0;
                for (values.clear(); !values.isEmpty(); values.remove(0)) {
                    seen += 1;
                }
                return seen;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "values.clear()" in result.source
    assert "while values:" in result.source
    assert "values.remove(0)" in result.source
    assert_valid_python(result.source)


def test_for_statement_multiple_assignment_initializers_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Loops {
            public int count(int limit) {
                int i;
                int j;
                int seen = 0;
                for (i = 0, j = limit; i < j; i++, j--) {
                    seen += 1;
                }
                return seen;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not _malformed_for_diagnostics(result)
    assert "i = 0" in result.source
    assert "j = limit" in result.source
    assert "while i < j:" in result.source
    assert "i += 1" in result.source
    assert "j -= 1" in result.source
    assert_valid_python(result.source)
    loops = _load_translated_class(result.source, "Loops")
    assert loops().count(4) == 2  # type: ignore[attr-defined,operator]


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


def test_label_only_statement_preserves_label_comment_and_translates_body() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Labels {
            public void check(int value) {
                positive:
                return;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "# label: positive" in result.source
    assert "return" in result.source
    assert "unsupported labeled_statement" not in result.source
    assert any(
        diagnostic.reason == "translated label-only statement"
        for diagnostic in result.diagnostics.handled
    )
    assert_valid_python(result.source)


def test_labeled_break_target_remains_explicitly_unsupported() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Labels {
            public void stop() {
                outer:
                while (true) {
                    break outer;
                }
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "# TODO(j2py): unsupported labeled_statement target outer" in result.source
    assert any(
        diagnostic.reason == "unsupported labeled break/continue target outer"
        for diagnostic in result.diagnostics.unhandled
    )
    assert_valid_python(result.source)


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
    assert "except (OSError, Exception) as ex:" in python_source
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


def test_empty_switch_statement_emits_pass_and_continues() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                switch (value) {
                }
                return 7;
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "pass" in result.source
    assert "return 7" in result.source
    assert_valid_python(result.source)
    switch_cls = _load_translated_class(result.source, "Switches")
    assert switch_cls().pick(1) == 7


def test_switch_statement_default_only_uses_explicit_guard() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                switch (value) {
                    default:
                        return 4;
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "if True:" in result.source
    assert "return 4" in result.source
    assert_valid_python(result.source)
    switch_cls = _load_translated_class(result.source, "Switches")
    assert switch_cls().pick(99) == 4


def test_switch_statement_fallthrough_to_case_then_default_preserves_semantics() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                int result = 0;
                switch (value) {
                    case 1:
                        result = 1;
                    case 2:
                        return result + 2;
                    default:
                        return result;
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "if value == 1:" in result.source
    assert "if value in (1, 2):" in result.source
    assert "elif value not in (1, 2):" in result.source
    assert_valid_python(result.source)
    switch_cls = _load_translated_class(result.source, "Switches")
    switch = switch_cls()
    assert switch.pick(1) == 3
    assert switch.pick(2) == 2
    assert switch.pick(3) == 0


def test_switch_statement_with_declaration_and_statement_block_translates() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                switch (value) {
                    case 1:
                        int local = value + 1;
                        return local;
                    default:
                        return 0;
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "if value == 1:" in result.source
    assert "local = value + 1" in result.source
    assert "return local" in result.source
    assert "else:" in result.source
    assert_valid_python(result.source)
    switch_cls = _load_translated_class(result.source, "Switches")
    switch = switch_cls()
    assert switch.pick(1) == 2
    assert switch.pick(2) == 0


def test_switch_statement_arrow_rules_translate_expression_and_throw_bodies() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                int result = 0;
                switch (value) {
                    case 1 -> result = 10;
                    default -> result = -1;
                }
                return result;
            }

            public int fail(int value) {
                switch (value) {
                    case 1 -> throw new IllegalArgumentException();
                    default -> { return 0; }
                }
            }
        }
        """,
    )

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "if value == 1:" in result.source
    assert "result = 10" in result.source
    assert "raise ValueError()" in result.source
    assert_valid_python(result.source)
    switch_cls = _load_translated_class(result.source, "Switches")
    switch = switch_cls()
    assert switch.pick(1) == 10
    assert switch.pick(2) == -1
    assert switch.fail(2) == 0
    with pytest.raises(ValueError):
        switch.fail(1)


def test_switch_statement_default_before_final_case_reports_explicit_diagnostic() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                switch (value) {
                    case 1:
                        return 1;
                    default:
                        return 0;
                    case 2:
                        return 2;
                }
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert (
        "TODO(j2py): switch default before final case requires manual translation" in result.source
    )
    assert any(
        item.reason == "switch default before final case requires manual translation"
        for item in result.diagnostics.unhandled
    )
    assert_valid_python(result.source)


def test_switch_statement_multiple_fallthrough_groups_report_explicit_diagnostic() -> None:
    result = translate_source_with_diagnostics(
        """
        public class Switches {
            public int pick(int value) {
                int result = 0;
                switch (value) {
                    case 1:
                        result += 1;
                    case 2:
                        result += 2;
                    case 3:
                        return result;
                    default:
                        return -1;
                }
            }
        }
        """,
    )

    assert result.coverage < 1.0
    assert "TODO(j2py): switch fall-through requires manual translation" in result.source
    assert any(
        item.reason == "switch fall-through requires manual translation"
        for item in result.diagnostics.unhandled
    )
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


def test_pattern_matching_switch_expression_uses_python_match_helper() -> None:
    parsed = parse_file(FIXTURES / "java" / "PatternMatchSwitch.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "match _j2py_subject:" in result.source
    assert "case int() as i:" in result.source
    assert "case str() as s if not s:" in result.source
    assert "case None:" in result.source
    assert "case _:" in result.source
    assert "__j2py_todo__" not in result.source
    assert_valid_python(result.source)


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

    # Canonical dedicated-lock idiom: `new Object()` must become a real object()
    # so the constructor doesn't raise NameError before the monitor helper runs.
    assert "self.monitor: object = object()" in result.source
    assert "with _j2py_monitor(self.monitor):" in result.source
    assert "from j2py_runtime import _j2py_monitor" in result.source
    assert any("_j2py_monitor" in warning.reason for warning in result.diagnostics.warnings)
    assert_module_executes(result.source)


def test_new_object_translates_to_object_call() -> None:
    python_source, _ = translate_source(
        """
        public class Holder {
            private final Object lock = new Object();
        }
        """,
    )

    assert "self.lock: object = object()" in python_source
    assert "Object()" not in python_source
    assert_module_executes(python_source)


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
    assert 'name = cast(str, item.get("name"))' in python_source
    assert "results.append(name)" in python_source
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
