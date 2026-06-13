"""Pipeline-level tests for LLM invocation and repair, using patched (cassette) responses.

These tests are NOT live_llm — they patch ``translate_with_llm`` with a hand-crafted
correct response so they run deterministically in CI without an API key. What they
verify:

1. The pipeline DOES invoke the LLM when the rule layer has unhandled constructs
   (coverage < 1.0).
2. The pipeline passes the rule-layer skeleton and diagnostics to the LLM.
3. The pipeline returns the LLM response as the final output.
4. For rule-layer bugs where coverage == 1.0 but output is wrong, the skeleton
   contains the expected broken pattern (so a future LLM-trigger improvement can
   be regression-tested).

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
    public void run() {
        assert 1 == 1 : "should hold";
        System.out.println("done");
    }
}
"""
    path = _write_java(tmp_path, java)

    cassette = (
        "class Probe:\n"
        "    def run(self) -> None:\n"
        "        assert 1 == 1\n"
        "        print('done')\n"
    )

    with patch("j2py.llm.client.translate_with_llm", return_value=cassette) as mock_llm:
        result = translate_file(path, cfg=CFG, use_llm=True, validate=False)

    assert result.used_llm, "LLM should have been invoked for assert_statement"
    mock_llm.assert_called_once()
    assert result.python_source == cassette


def test_pipeline_passes_skeleton_to_llm(tmp_path: Path) -> None:
    """translate_with_llm receives the rule-layer skeleton and diagnostics."""
    java = """\
public class Asserted {
    public void run() {
        assert 2 > 1 : "math broken";
    }
}
"""
    path = _write_java(tmp_path, java)
    captured: dict[str, str] = {}

    def capture(**kwargs: str) -> str:
        captured.update(kwargs)
        return "class Asserted:\n    def run(self) -> None:\n        assert 2 > 1\n"

    with patch("j2py.llm.client.translate_with_llm", side_effect=capture):
        translate_file(path, cfg=CFG, use_llm=True, validate=False)

    assert "partial_python" in captured
    assert "Asserted" in captured["partial_python"], "skeleton should contain the class name"
    assert "diagnostics" in captured
    assert "assert" in captured["diagnostics"].lower(), (
        "diagnostics should mention the unhandled assert_statement construct"
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
# Skeleton shape for rule-layer bugs: confirm the broken pattern is present
# so a future LLM-trigger fix can assert the LLM receives it
# ---------------------------------------------------------------------------

def test_skeleton_drops_arithmetic_parens() -> None:
    """Documents that (a + b) * 2 skeleton contains the broken a + b * 2 form.

    When the parentheses bug is fixed, this test will xpass and should be removed.
    """
    src, _ = translate_source("""
    public class Calc {
        public static int run(int a, int b) {
            return (a + b) * 2;
        }
    }
    """)
    assert "(a + b) * 2" not in src, (
        "Parentheses bug appears to be fixed — remove this assertion and update "
        "test_parenthesized_arithmetic_grouping_preserved in test_rule_layer_known_gaps.py"
    )
    assert "a + b * 2" in src or "a + b" in src


def test_skeleton_uses_float_divide_assign() -> None:
    """Documents that x /= 6 skeleton uses /= (float) not //= (int).

    When the compound-int-division bug is fixed, update accordingly.
    """
    src, _ = translate_source("""
    public class Div {
        public static int run() {
            int x = 20;
            x /= 6;
            return x;
        }
    }
    """)
    assert "/=" in src
    assert "//=" not in src


def test_skeleton_lowers_user_add_to_append() -> None:
    """Documents that user-defined .add() is incorrectly rewritten to .append().

    When the collection-lowering bug is fixed, update accordingly.
    """
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
    assert ".append(5)" in src


# ---------------------------------------------------------------------------
# Diagnostic accuracy: rule-layer gaps are accurately reported
# ---------------------------------------------------------------------------

def test_diagnostics_report_coverage_below_one_for_unhandled_construct() -> None:
    result = translate_source_with_diagnostics("""
    public class Unsup {
        public void run() {
            assert 1 == 1 : "should hold";
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
