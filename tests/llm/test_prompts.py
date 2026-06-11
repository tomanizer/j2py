"""Tests for LLM prompt construction."""

from j2py.llm.prompts import build_translation_prompt


def test_build_translation_prompt_includes_context_source_and_partial() -> None:
    system, messages = build_translation_prompt(
        java_source="public class A {}",
        partial_python="class A:\n    pass\n",
        context="package com.example",
        diagnostics="line 3: unsupported lambda_expression",
        validation_feedback="SyntaxError: bad output",
    )

    assert "Java-to-Python translator" in system
    content = messages[0]["content"]
    assert "<project_context>" in content
    assert "package com.example" in content
    assert "<rule_diagnostics>" in content
    assert "unsupported lambda_expression" in content
    assert "<validation_feedback>" in content
    assert "SyntaxError: bad output" in content
    assert "<java_source>" in content
    assert "public class A {}" in content
    assert "<partial_translation>" in content
    assert "class A:" in content
    assert "reviewable, fully working Python" in content
    assert "preserves the Java structure" in content


def test_system_prompt_frames_llm_as_structural_transposer() -> None:
    system, _ = build_translation_prompt(
        java_source="public class A {}",
        partial_python="class A:\n    pass\n",
    )

    assert "conservative code transposer" in system
    assert "Preserve class, method, field, and statement ordering" in system
    assert "Preserve the Java control-flow shape" in system
    assert "not a Python refactoring assistant" in system
    assert "do not rewrite algorithms" in system
