"""On-demand exploratory end-to-end LLM tests.

These tests exercise the real layered pipeline (tree-sitter parse -> rule-based
skeleton -> LLM completion) against either synthetic or real Spring code.

They deliberately make live calls to the Anthropic API. They are excluded from
normal pytest runs, make check, and CI by the live_llm marker in pyproject.toml.

Typical usage:
    ANTHROPIC_API_KEY=sk-... uv run pytest -m live_llm tests/llm/test_e2e_llm.py -v -s
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.parse.java_ast import parse_source
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.skeleton import translate_skeleton_with_diagnostics

REPO_ROOT = Path(__file__).parents[2]
SPRING_CORPUS = REPO_ROOT / ".corpus" / "spring-framework"
NEEDS_API_KEY = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
NEEDS_SPRING = pytest.mark.skipif(
    not SPRING_CORPUS.exists(),
    reason=f"Spring corpus not found at {SPRING_CORPUS}",
)
LIVE_LLM = pytest.mark.live_llm


@NEEDS_API_KEY
@LIVE_LLM
def test_llm_completes_skeleton_from_tree_sitter() -> None:
    """A tiny synthetic Java class goes through skeleton generation before the LLM."""
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

    parsed = parse_source(java)
    symbols = extract_symbols(parsed)
    cfg = ConfigLoader().add_defaults().build()
    skeleton_result = translate_skeleton_with_diagnostics(parsed, symbols, cfg)

    print("\n=== RULE SKELETON ===")
    print(skeleton_result.source)
    print("=== DIAGNOSTICS ===")
    print("coverage:", skeleton_result.coverage)
    print("unhandled:", [d.reason for d in skeleton_result.diagnostics.unhandled])

    result = translate_with_llm(
        java_source=java,
        partial_python=skeleton_result.source,
        diagnostics=_format_diagnostics(skeleton_result.diagnostics),
        use_cache=False,
    )

    print("\n=== FINAL LLM OUTPUT ===")
    print(result)

    ast.parse(result)
    assert "class Greeter" in result or "class greeter" in result.lower()
    assert "greet" in result


@NEEDS_API_KEY
@LIVE_LLM
def test_prompt_cache_reports_second_call_cache_hit() -> None:
    """Two identical direct SDK calls should create then read the system prompt cache."""
    from j2py.llm.client import get_client
    from j2py.llm.prompts import build_translation_prompt

    java = "public class CacheProbe { public int value() { return 1; } }"
    system, messages = build_translation_prompt(
        java_source=java,
        partial_python="class CacheProbe:\n    def value(self) -> int:\n        pass\n",
    )
    model = os.environ.get("J2PY_LIVE_LLM_MODEL", "claude-sonnet-4-6")

    first = get_client().messages.create(
        model=model,
        max_tokens=64,
        system=system,
        messages=messages,  # type: ignore[arg-type]
    )
    second = get_client().messages.create(
        model=model,
        max_tokens=64,
        system=system,
        messages=messages,  # type: ignore[arg-type]
    )

    print("\n=== PROMPT CACHE USAGE ===")
    print("first cache_creation_input_tokens:", first.usage.cache_creation_input_tokens)
    print("first cache_read_input_tokens:", first.usage.cache_read_input_tokens)
    print("second cache_creation_input_tokens:", second.usage.cache_creation_input_tokens)
    print("second cache_read_input_tokens:", second.usage.cache_read_input_tokens)

    assert system[0]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert (second.usage.cache_read_input_tokens or 0) > 0


def _format_diagnostics(diagnostics: TranslationDiagnostics) -> str:
    if not diagnostics.unhandled:
        return "No unresolved constructs from the rule layer."
    return "\n".join(
        f"- line {item.line}: {item.node_type} - {item.reason}"
        for item in diagnostics.unhandled
    )


@NEEDS_API_KEY
@NEEDS_SPRING
@LIVE_LLM
def test_full_pipeline_on_spring_aot_detector() -> None:
    """translate_file() with use_llm=True on a real Spring source file."""
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
@LIVE_LLM
def test_pipeline_output_has_no_markdown_fences() -> None:
    """LLM responses must not contain raw markdown fences in the final output."""
    from j2py.pipeline import translate_file

    path = SPRING_CORPUS / "spring-core/src/main/java/org/springframework/aot/AotDetector.java"
    cfg = ConfigLoader().add_defaults().build()
    result = translate_file(path, cfg=cfg, use_llm=True, validate=False)

    assert "```" not in result.python_source, (
        "Markdown fences leaked into translation output:\n" + result.python_source[:500]
    )


LLM_GAP_PROBE_CASES = [
    pytest.param(
        REPO_ROOT / "tests/fixtures/corpus/constructs/AdvancedStreams.java",
        [
            ".stream()",
            "List.stream",
            "collectors.grouping_by",
            "unsupported stream intermediate",
        ],
        True,
        id="advanced-streams",
    ),
    pytest.param(
        SPRING_CORPUS
        / "spring-context/src/main/java/org/springframework/jmx/support/ObjectNameManager.java",
        [
            'NotImplementedError("j2py overload dispatch required")',
            "overloaded method get_instance requires manual dispatch",
        ],
        True,
        marks=NEEDS_SPRING,
        id="object-name-manager-overloads",
    ),
]


@NEEDS_API_KEY
@LIVE_LLM
@pytest.mark.parametrize(("path", "forbidden_fragments", "require_mypy"), LLM_GAP_PROBE_CASES)
def test_llm_probe_known_static_gap_files(
    path: Path,
    forbidden_fragments: list[str],
    require_mypy: bool,
) -> None:
    """Probe whether live LLM completion resolves current static rule-layer gaps.

    This is intentionally an on-demand smoke test, not part of `make check`. It exercises
    real files that the deterministic skeleton still cannot fully translate and verifies
    that the LLM result at least removes the specific static failure markers.
    """
    from j2py.pipeline import translate_file

    cfg = ConfigLoader().add_defaults().build()
    result = translate_file(path, cfg=cfg, use_llm=True, validate=True)

    print("\n=== LIVE LLM GAP PROBE ===")
    print("file:", path)
    print("confidence:", result.confidence)
    print("used_llm:", result.used_llm)
    if result.diagnostics is not None:
        print("skeleton unhandled:")
        for item in result.diagnostics.unhandled:
            print(f"  line {item.line}: {item.node_type} - {item.reason}")
    if result.validation is not None:
        print("validation syntax_ok:", result.validation.syntax_ok)
        print("validation mypy_ok:", result.validation.mypy_ok)
        for error in result.validation.syntax_errors + result.validation.mypy_errors[:5]:
            print("  validation:", error)
    if result.structural_verification is not None:
        print("structural ok:", result.structural_verification.ok)
        for error in result.structural_verification.errors:
            print("  structural:", error)
    print("=== FINAL LLM OUTPUT ===")
    print(result.python_source)

    assert result.used_llm, "LLM should have been invoked for the selected static gap file"
    ast.parse(result.python_source)
    assert "```" not in result.python_source
    if require_mypy:
        assert result.validation is not None
        assert result.validation.mypy_ok, result.validation.mypy_errors
    for fragment in forbidden_fragments:
        assert fragment not in result.python_source
