"""On-demand exploratory end-to-end LLM tests.

These tests exercise the real layered pipeline (tree-sitter parse -> rule-based
skeleton -> LLM completion) against small probe fixtures or real Spring code.

They deliberately make live calls to the Anthropic API. They are excluded from
normal pytest runs, make check, and CI by the live_llm marker in pyproject.toml.

Typical usage:
    export ANTHROPIC_API_KEY=sk-...
    make test-llm-e2e

Or create a local ``.env`` from ``.env.example`` — ``make test-llm-e2e`` loads it
automatically when the variable is not already exported.

Direct pytest:
    ANTHROPIC_API_KEY=sk-... uv run pytest -m live_llm tests/llm/test_e2e_llm.py -v -s
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from j2py.analyze.symbols import extract_symbols
from j2py.config.loader import ConfigLoader
from j2py.dotenv import load_repo_dotenv
from j2py.parse.java_ast import parse_source
from j2py.pipeline import translate_file
from j2py.translate.diagnostics import TranslationDiagnostics
from j2py.translate.skeleton import translate_skeleton_with_diagnostics
from scripts.corpus.corpus_presets import corpus_checkout_root
from tests.conftest import LLM_FIXTURES

load_repo_dotenv()

REPO_ROOT = Path(__file__).parents[2]
SPRING_CORPUS = corpus_checkout_root() / "spring-framework"
NEEDS_API_KEY = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
NEEDS_SPRING = pytest.mark.skipif(
    not SPRING_CORPUS.exists(),
    reason=f"Spring corpus not found at {SPRING_CORPUS}",
)
LIVE_LLM = pytest.mark.live_llm


@dataclass(frozen=True)
class LlmProbeCase:
    """One live-LLM smoke scenario: file, expectations, and how the skeleton fails."""

    path: Path
    trigger: str
    forbidden_fragments: tuple[str, ...]
    expected_fragments: tuple[str, ...] = ()
    require_mypy: bool = True


def _format_diagnostics(diagnostics: TranslationDiagnostics) -> str:
    if not diagnostics.unhandled:
        return "No unresolved constructs from the rule layer."
    return "\n".join(
        f"- line {item.line}: {item.node_type} - {item.reason}" for item in diagnostics.unhandled
    )


def _report_pipeline_result(*, label: str, path: Path, result: object) -> None:
    from j2py.pipeline import TranslationResult

    assert isinstance(result, TranslationResult)
    print(f"\n=== {label} ===")
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


def _assert_live_probe_result(
    *,
    path: Path,
    result: object,
    forbidden_fragments: tuple[str, ...],
    expected_fragments: tuple[str, ...],
    require_mypy: bool,
) -> None:
    from j2py.pipeline import TranslationResult

    assert isinstance(result, TranslationResult)
    assert result.used_llm, f"LLM should have been invoked for {path.name}"
    ast.parse(result.python_source)
    assert "```" not in result.python_source
    if require_mypy:
        assert result.validation is not None
        assert result.validation.mypy_ok, result.validation.mypy_errors
    for fragment in forbidden_fragments:
        assert fragment not in result.python_source, (
            f"Skeleton failure marker still present in LLM output: {fragment!r}"
        )
    for fragment in expected_fragments:
        assert fragment in result.python_source, (
            f"Expected translated fragment missing from LLM output: {fragment!r}"
        )


# ---------------------------------------------------------------------------
# Direct LLM client smoke (skeleton -> translate_with_llm)
# ---------------------------------------------------------------------------


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

    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # Prompt cache hits are best-effort: the second call should reuse or extend cache state.
    second_cache_read = second.usage.cache_read_input_tokens or 0
    second_cache_create = second.usage.cache_creation_input_tokens or 0
    first_cache_read = first.usage.cache_read_input_tokens or 0
    first_cache_create = first.usage.cache_creation_input_tokens or 0
    assert (second_cache_read + second_cache_create + first_cache_read + first_cache_create) > 0, (
        "Expected Anthropic prompt cache activity on at least one call"
    )


# ---------------------------------------------------------------------------
# Full pipeline on real Spring source
# ---------------------------------------------------------------------------


@NEEDS_API_KEY
@NEEDS_SPRING
@LIVE_LLM
def test_full_pipeline_on_spring_aot_detector() -> None:
    """translate_file() with use_llm=True on a real Spring source file."""
    from j2py.validate.checks import validate_source

    path = SPRING_CORPUS / "spring-core/src/main/java/org/springframework/aot/AotDetector.java"
    assert path.exists(), f"Expected Spring file missing: {path}"

    cfg = ConfigLoader().add_defaults().build()
    result = translate_file(path, cfg=cfg, use_llm=True, validate=True)

    assert result.used_llm, "LLM should have been invoked"
    ast.parse(result.python_source)
    assert "AotDetector" in result.python_source
    assert "use_generated_artifacts" in result.python_source
    check = validate_source(result.python_source)
    assert check.syntax_ok, f"LLM output has syntax errors: {check.syntax_errors}"
    assert check.mypy_ok, f"LLM output has type errors: {check.mypy_errors}"


@NEEDS_API_KEY
@NEEDS_SPRING
@LIVE_LLM
def test_pipeline_output_has_no_markdown_fences() -> None:
    """LLM responses must not contain raw markdown fences in the final output."""
    path = SPRING_CORPUS / "spring-core/src/main/java/org/springframework/aot/AotDetector.java"
    cfg = ConfigLoader().add_defaults().build()
    result = translate_file(path, cfg=cfg, use_llm=True, validate=False)

    assert "```" not in result.python_source, (
        "Markdown fences leaked into translation output:\n" + result.python_source[:500]
    )


# ---------------------------------------------------------------------------
# Parametrised gap probes: small fixtures + known static failures
# ---------------------------------------------------------------------------

LLM_GAP_PROBE_CASES = [
    pytest.param(
        LlmProbeCase(
            path=LLM_FIXTURES / "AssertProbe.java",
            trigger="coverage_gap",
            forbidden_fragments=("TODO(j2py): unsupported assert_statement",),
            expected_fragments=("assert value > 0",),
            require_mypy=True,
        ),
        id="assert-probe",
    ),
    pytest.param(
        LlmProbeCase(
            path=LLM_FIXTURES / "MultiDimArray.java",
            trigger="coverage_gap",
            forbidden_fragments=("return __j2py_todo__",),
            expected_fragments=("create",),
            require_mypy=True,
        ),
        id="multi-dim-array",
    ),
    pytest.param(
        LlmProbeCase(
            path=LLM_FIXTURES / "AnonymousComparator.java",
            trigger="mypy_repair",
            forbidden_fragments=("from com.example.Integer import Integer",),
            expected_fragments=("compare", "by_length"),
            require_mypy=True,
        ),
        id="anonymous-comparator",
    ),
    pytest.param(
        LlmProbeCase(
            path=REPO_ROOT / "tests/fixtures/corpus/constructs/AdvancedStreams.java",
            trigger="mypy_repair",
            forbidden_fragments=(
                ".stream()",
                "List.stream",
                "collectors.grouping_by",
                "unsupported stream intermediate",
            ),
            expected_fragments=("flat_map_example", "reduce_example"),
            require_mypy=True,
        ),
        id="advanced-streams",
    ),
    pytest.param(
        LlmProbeCase(
            path=REPO_ROOT / "tests/fixtures/corpus/constructs/AnonymousAndInner.java",
            trigger="mypy_repair",
            forbidden_fragments=("from org.springframework.example.Integer import Integer",),
            expected_fragments=("length_comparator", "make_task"),
            require_mypy=True,
        ),
        id="anonymous-and-inner",
    ),
    pytest.param(
        LlmProbeCase(
            path=REPO_ROOT / "tests/fixtures/corpus/constructs/InterfaceDefaults.java",
            trigger="mypy_repair",
            # Skeleton leaves T/U/Consumer undefined. A good LLM fix defines TypeVar(s)
            # and a Consumer placeholder — it may still mention Consumer[U] in annotations.
            forbidden_fragments=(),
            expected_fragments=("handle_default", "logging", "TypeVar", "class Consumer"),
            require_mypy=False,
        ),
        id="interface-defaults",
    ),
    pytest.param(
        LlmProbeCase(
            path=SPRING_CORPUS
            / "spring-context/src/main/java/org/springframework/jmx/support/ObjectNameManager.java",
            trigger="mypy_repair",
            forbidden_fragments=(
                'NotImplementedError("j2py overload dispatch required")',
                "overloaded method get_instance requires manual dispatch",
            ),
            expected_fragments=("ObjectNameManager",),
            require_mypy=True,
        ),
        marks=NEEDS_SPRING,
        id="object-name-manager-overloads",
    ),
]


@NEEDS_API_KEY
@LIVE_LLM
@pytest.mark.parametrize("case", LLM_GAP_PROBE_CASES)
def test_llm_probe_known_static_gap_files(case: LlmProbeCase) -> None:
    """Probe whether live LLM completion resolves current static rule-layer gaps.

    Each case targets a file where the deterministic skeleton either leaves
    unhandled constructs (coverage < 1.0) or produces mypy-invalid Python
    (coverage == 1.0). The test prints skeleton diagnostics and final output
    so you can inspect what the LLM changed.
    """
    cfg = ConfigLoader().add_defaults().build()
    skeleton_only = translate_file(case.path, cfg=cfg, use_llm=False, validate=True)
    print("\n=== RULE SKELETON (before LLM) ===")
    print("trigger:", case.trigger)
    print("coverage:", skeleton_only.confidence)
    if skeleton_only.validation is not None:
        print("skeleton mypy_ok:", skeleton_only.validation.mypy_ok)
        for error in skeleton_only.validation.mypy_errors[:5]:
            print("  skeleton mypy:", error)
    print(skeleton_only.python_source)

    result = translate_file(case.path, cfg=cfg, use_llm=True, validate=True)
    _report_pipeline_result(label="LIVE LLM GAP PROBE", path=case.path, result=result)
    _assert_live_probe_result(
        path=case.path,
        result=result,
        forbidden_fragments=case.forbidden_fragments,
        expected_fragments=case.expected_fragments,
        require_mypy=case.require_mypy,
    )
