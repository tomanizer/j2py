"""Pipeline-level tests for LLM invocation and repair, using patched (cassette) responses.

These tests are NOT live_llm — they patch ``translate_with_llm`` with a hand-crafted
correct response so they run deterministically in CI without an API key. What they
verify:

1. The pipeline DOES invoke the LLM when the rule layer has unhandled constructs
   (coverage < 1.0).
2. The pipeline passes the rule-layer skeleton and diagnostics to the LLM.
3. The pipeline returns the LLM response as the final output.
4. Previously fixed rule-layer bug classes remain covered by direct skeleton
   assertions so they do not silently regress.

These tests run in the normal ``make check`` suite (no special marker needed).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from j2py.config.loader import ConfigLoader
from j2py.pipeline import translate_file
from tests.translate.skeleton.helpers import translate_source, translate_source_with_diagnostics

CFG = ConfigLoader().add_defaults().build()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_java(tmp_path: Path, source: str, filename: str = "Main.java") -> Path:
    p = tmp_path / filename
    p.write_text(source, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Pipeline invocation: LLM is called when rule layer has coverage < 1.0
# ---------------------------------------------------------------------------


def test_pipeline_invokes_llm_for_unhandled_constructs(tmp_path: Path) -> None:
    """translate_file with use_llm=True calls translate_with_llm when coverage < 1.0."""
    java = """\
public class Probe {
    public void value() {
        done:
        while (true) {
            break done;
        }
    }
}
"""
    path = _write_java(tmp_path, java)

    cassette = (
        "class Probe:\n    def value(self) -> None:\n        while True:\n            break\n"
    )

    with patch("j2py.llm.client.translate_with_llm", return_value=cassette) as mock_llm:
        result = translate_file(path, cfg=CFG, use_llm=True, validate=False)

    assert result.used_llm, "LLM should have been invoked for labeled_statement"
    mock_llm.assert_called_once()
    assert result.python_source == cassette


def test_pipeline_passes_skeleton_to_llm(tmp_path: Path) -> None:
    """translate_with_llm receives the rule-layer skeleton and diagnostics."""
    java = """\
public class Matrix {
    public void value() {
        done:
        while (true) {
            break done;
        }
    }
}
"""
    path = _write_java(tmp_path, java)
    captured: dict[str, str] = {}

    def capture(**kwargs: str) -> str:
        captured.update(kwargs)
        return "class Matrix:\n    def value(self) -> int:\n        return 1\n"

    with patch("j2py.llm.client.translate_with_llm", side_effect=capture):
        translate_file(path, cfg=CFG, use_llm=True, validate=False)

    assert "partial_python" in captured
    assert "Matrix" in captured["partial_python"], "skeleton should contain the class name"
    assert "diagnostics" in captured
    assert "unsupported labeled break/continue target done" in captured["diagnostics"], (
        "diagnostics should mention the unhandled labeled jump target"
    )


def test_pipeline_skips_llm_when_rule_layer_is_complete(tmp_path: Path) -> None:
    """translate_file does NOT call the LLM when the rule layer covers everything."""
    java = """\
public class Pure {
    public static int add(int a, int b) {
        return a + b;
    }
}
"""
    path = _write_java(tmp_path, java)

    with patch("j2py.llm.client.translate_with_llm") as mock_llm:
        result = translate_file(path, cfg=CFG, use_llm=True, validate=False)

    mock_llm.assert_not_called()
    assert not result.used_llm
    assert "def add(" in result.python_source


# ---------------------------------------------------------------------------
# Skeleton shape for previously fixed rule-layer bugs
# ---------------------------------------------------------------------------


def test_skeleton_preserves_arithmetic_parens() -> None:
    """Regression guard for parenthesized arithmetic grouping."""
    src, _ = translate_source("""
    public class Calc {
        public static int run(int a, int b) {
            return (a + b) * 2;
        }
    }
    """)
    assert "(a + b) * 2" in src


def test_skeleton_uses_truncating_int_divide_assign() -> None:
    """Regression guard for Java int compound division."""
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


def test_skeleton_keeps_user_add_method_call() -> None:
    """Regression guard for user-defined add methods on non-collection receivers."""
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


# ---------------------------------------------------------------------------
# Diagnostic accuracy: rule-layer gaps are accurately reported
# ---------------------------------------------------------------------------


def test_diagnostics_report_coverage_below_one_for_unhandled_construct() -> None:
    result = translate_source_with_diagnostics("""
    public class Unsup {
        public int value() {
            done:
            while (true) {
                break done;
            }
            return 1;
        }
    }
    """)
    assert result.coverage < 1.0
    assert result.diagnostics.unhandled


def test_diagnostics_coverage_is_one_for_fully_handled_class() -> None:
    result = translate_source_with_diagnostics("""
    public class Simple {
        private int x;
        public Simple(int x) { this.x = x; }
        public int getX() { return this.x; }
    }
    """)
    assert result.coverage == 1.0
    assert not result.diagnostics.unhandled
