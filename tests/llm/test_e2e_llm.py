"""End-to-end LLM pipeline tests — require ANTHROPIC_API_KEY to be set.

Run with:
    ANTHROPIC_API_KEY=sk-... uv run python -m pytest tests/llm/test_e2e_llm.py -v -s
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

SPRING_CORPUS = Path(__file__).parents[2] / ".corpus" / "spring-framework"
NEEDS_API_KEY = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
NEEDS_SPRING = pytest.mark.skipif(
    not SPRING_CORPUS.exists(),
    reason=f"Spring corpus not found at {SPRING_CORPUS}",
)


@NEEDS_API_KEY
def test_llm_translates_simple_java_class() -> None:
    """A tiny synthetic Java class → valid Python via the full pipeline."""
    from j2py.llm.client import translate_with_llm

    java = """\
package com.example;

public class Greeter {
    private final String name;

    public Greeter(String name) {
        this.name = name;
    }

    public String greet() {
        return "Hello, " + name + "!";
    }
}
"""
    result = translate_with_llm(
        java_source=java,
        partial_python="",
        use_cache=False,
    )
    # Must be parseable Python
    ast.parse(result)
    # Must define a Greeter class
    assert "class Greeter" in result or "class greeter" in result.lower()
    assert "greet" in result


@NEEDS_API_KEY
@NEEDS_SPRING
def test_full_pipeline_on_spring_aot_detector() -> None:
    """translate_file() with use_llm=True on a real Spring source file."""
    from j2py.config.loader import ConfigLoader
    from j2py.pipeline import translate_file
    from j2py.validate.checks import validate_source

    path = SPRING_CORPUS / "spring-core/src/main/java/org/springframework/aot/AotDetector.java"
    assert path.exists(), f"Expected Spring file missing: {path}"

    cfg = ConfigLoader().add_defaults().build()
    result = translate_file(path, cfg=cfg, use_llm=True, validate=True)

    assert result.used_llm, "LLM should have been invoked"
    # Output must parse as valid Python
    ast.parse(result.python_source)
    # Must define the class
    assert "AotDetector" in result.python_source
    # Method should appear
    assert "use_generated_artifacts" in result.python_source
    # Undefined names from skeleton should be resolved
    check = validate_source(result.python_source)
    assert check.syntax_ok, f"LLM output has syntax errors: {check.syntax_errors}"
    assert check.mypy_ok, f"LLM output has type errors: {check.mypy_errors}"


@NEEDS_API_KEY
@NEEDS_SPRING
def test_pipeline_output_has_no_markdown_fences() -> None:
    """LLM responses must not contain raw markdown fences in the final output."""
    from j2py.config.loader import ConfigLoader
    from j2py.pipeline import translate_file

    path = SPRING_CORPUS / "spring-core/src/main/java/org/springframework/aot/AotDetector.java"
    cfg = ConfigLoader().add_defaults().build()
    result = translate_file(path, cfg=cfg, use_llm=True, validate=False)

    assert "```" not in result.python_source, (
        "Markdown fences leaked into translation output:\n" + result.python_source[:500]
    )
