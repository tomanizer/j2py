"""Unit tests documenting known rule-layer translation bugs.

Each test covers a previously broken semantic translation edge so the rule layer cannot
regress silently.

These tests are fast (no JDK, no LLM, no subprocess) and run in the normal suite via
``make check``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from j2py.analyze.symbols import extract_symbols
from j2py.parse.java_ast import parse_file
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from tests.translate.skeleton.helpers import (
    CFG,
    translate_source,
    translate_source_with_diagnostics,
)

CFG_FIXTURES = Path(__file__).parents[1] / "fixtures"

# ---------------------------------------------------------------------------
# Bug 1: Parentheses dropped in arithmetic expressions
# ---------------------------------------------------------------------------


def test_parenthesized_arithmetic_grouping_preserved() -> None:
    """(a + b) * 2 must translate with grouping intact, not drop the parens."""
    src, _ = translate_source("""
    public class Calc {
        public static int run(int a, int b) {
            return (a + b) * 2;
        }
    }
    """)
    assert "(a + b) * 2" in src


def test_nested_parenthesized_grouping_preserved() -> None:
    src, _ = translate_source("""
    public class Calc {
        public static int run(int a, int b, int c, int d) {
            return (a - b) * (c + d);
        }
    }
    """)
    assert "(a - b) * (c + d)" in src


def test_right_hand_division_grouping_preserved_under_multiplication() -> None:
    src, _ = translate_source("""
    public class Calc {
        public static int run(int a, int b, int c) {
            return a * (b / c);
        }
    }
    """)
    assert "a * (b // c)" in src
    assert "a * b // c" not in src


# ---------------------------------------------------------------------------
# Bug 2: Compound integer division emits /= (float) instead of truncating int division
# ---------------------------------------------------------------------------


def test_compound_int_division_uses_truncating_helper() -> None:
    """x /= 6 on a Java int must truncate toward zero, not use Python /= or //=."""
    src, _ = translate_source("""
    public class Div {
        public static int run() {
            int x = 20;
            x /= 6;
            return x;
        }
    }
    """)
    assert "from j2py_runtime import _j2py_idiv" in src
    assert "x = _j2py_idiv(x, 6)" in src
    assert "//=" not in src
    assert "/=" not in src


def test_compound_negative_int_division_uses_truncating_helper() -> None:
    src, _ = translate_source("""
    public class Div {
        public static int run() {
            int x = -20;
            x /= 6;
            return x;
        }
    }
    """)
    assert "x = -20" in src
    assert "x = _j2py_idiv(x, 6)" in src


# ---------------------------------------------------------------------------
# Bug 3: Collection-method lowering fires on user-defined .add() methods
# ---------------------------------------------------------------------------


def test_user_defined_add_method_not_lowered_to_append() -> None:
    src, _ = translate_source("""
    public class Counter {
        private int value = 0;
        public void add(int n) { value += n; }
        public int getValue() { return value; }
        public static void main(String[] args) {
            Counter c = new Counter();
            c.add(5);
        }
    }
    """)
    assert ".add(5)" in src or ".add(" in src
    assert ".append(5)" not in src


def test_list_field_add_still_lowers_to_append() -> None:
    src, _ = translate_source("""
    import java.util.ArrayList;
    import java.util.List;

    public class Names {
        private List<String> values = new ArrayList<>();
        public void addName(String value) {
            values.add(value);
        }
    }
    """)
    assert "self.values.append(value)" in src
    assert "self.values.add(value)" not in src


# ---------------------------------------------------------------------------
# Bug 4: Builtin-clash rename renames def but not call site
# ---------------------------------------------------------------------------


def test_builtin_clash_rename_consistent_at_def_and_call_site() -> None:
    """A user method named 'sum' must have matching name at def and call site."""
    src, _ = translate_source("""
    public class Stats {
        public int sum(int a, int b) { return a + b; }
        public static void main(String[] args) {
            Stats s = new Stats();
            System.out.println(s.sum(3, 4));
        }
    }
    """)
    has_def_sum_ = "def sum_(" in src
    has_call_sum_ = ".sum_(" in src
    has_def_sum = "def sum(" in src
    has_call_sum = ".sum(" in src
    assert (has_def_sum_ and has_call_sum_) or (has_def_sum and has_call_sum), (
        f"def and call site names diverge:\ndef sum_={has_def_sum_}, call .sum_={has_call_sum_}, "
        f"def sum={has_def_sum}, call .sum={has_call_sum}\n\n{src}"
    )


def test_builtin_clash_rename_consistent_for_sibling_top_level_class() -> None:
    src, _ = translate_source("""
    class Stats {
        public int sum(int a, int b) { return a + b; }
    }
    public class UseStats {
        public static void main(String[] args) {
            Stats s = new Stats();
            System.out.println(s.sum(3, 4));
        }
    }
    """)
    assert "def sum_(" in src
    assert ".sum_(3, 4)" in src
    assert ".sum(3, 4)" not in src


def test_builtin_clash_rename_consistent_for_same_class_receiver() -> None:
    src, _ = translate_source("""
    public class Stats {
        public int sum(int a, int b) { return a + b; }
        public int call(Stats other) {
            return other.sum(3, 4);
        }
    }
    """)
    assert "def sum_(" in src
    assert "return other.sum_(3, 4)" in src


def test_LineCommentInExpression_fixture_translates_without_unhandled_diagnostics() -> None:
    parsed = parse_file(CFG_FIXTURES / "corpus" / "constructs" / "LineCommentInExpression.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "return [0, 1, 2]" in result.source
    assert 'return ["alpha", "beta"]' in result.source
    assert "# nop" not in result.source
    assert "# first" not in result.source
    assert "unsupported expression line_comment" not in result.source
    assert "__j2py_todo__" not in result.source


def test_AmbiguousGetProbe_fixture_translates_without_unhandled_diagnostics() -> None:
    parsed = parse_file(CFG_FIXTURES / "corpus" / "constructs" / "AmbiguousGetProbe.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "return calendar.get(Calendar.DAY_OF_MONTH)" in result.source
    assert "return values[index]" in result.source
    assert "return values.get(key)" in result.source
    assert "ambiguous get invocation requires receiver collection type" not in result.source
    assert "__j2py_todo__" not in result.source


def test_ApiGetReceivers_fixture_translates_without_unhandled_diagnostics() -> None:
    parsed = parse_file(CFG_FIXTURES / "corpus" / "constructs" / "ApiGetReceivers.java")
    result = translate_skeleton_with_diagnostics(parsed, extract_symbols(parsed), CFG)

    ast.parse(result.source)
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
    assert "return self.byte_buffer.get(index)" in result.source
    assert "return self.counts.get(index)" in result.source
    assert "return values.get(index)" in result.source
    assert "byte_buffer[index]" not in result.source
    assert "ambiguous get invocation requires receiver collection type" not in result.source
    assert "__j2py_todo__" not in result.source


# ---------------------------------------------------------------------------
# Bug 5: for-loop with <= bound falls back to while-loop where continue skips increment
# ---------------------------------------------------------------------------


def test_for_loop_le_bound_with_continue_translates_to_range() -> None:
    """for (int i=1; i<=5; i++) with a continue must not produce a while-loop."""
    src, _ = translate_source("""
    public class Loop {
        public static int run() {
            int total = 0;
            for (int i = 1; i <= 5; i++) {
                if (i == 3) continue;
                total += i;
            }
            return total;
        }
    }
    """)
    assert "for i in range(" in src
    assert "while" not in src


def test_for_loop_le_bound_parenthesizes_non_atomic_stop() -> None:
    src, _ = translate_source("""
    public class Loop {
        public static int run(boolean flag) {
            int total = 0;
            for (int i = 0; i <= (flag ? 2 : 3); i++) {
                total += i;
            }
            return total;
        }
    }
    """)
    assert "for i in range(0, (2 if flag else 3) + 1):" in src
    assert "for i in range(0, 2 if flag else 3 + 1):" not in src


def test_outer_capturing_nested_class_constructor_passes_self_with_args() -> None:
    src, _ = translate_source("""
    public class Outer {
        private int base = 2;
        class Inner {
            private int value;
            Inner(int value) { this.value = value; }
            int total() { return Outer.this.base + value; }
        }
        public int run() {
            Inner inner = new Inner(3);
            return inner.total();
        }
    }
    """)
    assert "inner = self.Inner(self, 3)" in src


# ---------------------------------------------------------------------------
# Diagnostic accuracy: graduated assert statements are handled by the rule layer
# ---------------------------------------------------------------------------


def test_assert_statement_translates_without_unhandled_diagnostic() -> None:
    result = translate_source_with_diagnostics("""
    public class Probe {
        public void run() {
            assert 1 == 1 : "unreachable";
            assert true;
        }
    }
    """)
    assert 'assert 1 == 1, "unreachable"' in result.source
    assert "assert True" in result.source
    assert not any(d.node_type == "assert_statement" for d in result.diagnostics.unhandled)
    assert result.coverage == 1.0
