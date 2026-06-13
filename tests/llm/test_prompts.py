"""Tests for LLM prompt construction."""

from j2py.llm.prompts import build_translation_prompt


def test_build_translation_prompt_includes_context_source_and_partial() -> None:
    system, messages = build_translation_prompt(
        java_source="public class A {}",
        partial_python="class A:\n    pass\n",
        context="package com.example",
        diagnostics="line 3: unsupported lambda_expression",
        validation_feedback="SyntaxError: bad output",
        previous_python="def broken(:\n",
    )

    assert len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert "Java-to-Python translator" in system[0]["text"]
    content = messages[0]["content"]
    assert "<project_context>" in content
    assert "package com.example" in content
    assert "<rule_diagnostics>" in content
    assert "unsupported lambda_expression" in content
    assert "<validation_feedback>" in content
    assert "SyntaxError: bad output" in content
    assert "<previous_llm_output>" in content
    assert "def broken(:" in content
    assert "Repair that Python output" in content
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

    system_text = system[0]["text"]
    assert "conservative code transposer" in system_text
    assert "Preserve class, method, field, and statement ordering" in system_text
    assert "Preserve the Java control-flow shape" in system_text
    assert "not a Python refactoring assistant" in system_text
    assert "do not rewrite algorithms" in system_text
    assert "positional-only" in system_text
    assert "Do NOT import unresolved Java platform/framework packages" in system_text
    assert "Never wrap unresolved Java imports in try/except ImportError" in system_text
    assert "overload signatures remain distinct" in system_text
    assert "same-arity Java overloads" in system_text
