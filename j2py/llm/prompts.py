"""Structured prompts for LLM-assisted Java→Python translation."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

PROMPT_VERSION = "j2py-translation-v8"
REVIEW_PROMPT_VERSION = "j2py-review-v1"
ADVICE_PROMPT_VERSION = "j2py-doctor-advice-v1"


class TextPromptBlock(TypedDict):
    """Provider-neutral text block used by LLM clients."""

    type: str
    text: str
    cache_control: NotRequired[dict[str, str]]


SYSTEM_PROMPT = (
    """\
You are an expert Java-to-Python translator and a conservative code transposer, not a \
Python refactoring assistant. Your goal is to produce Python code that is semantically \
and functionally equivalent to the input Java, with line-level structural correspondence \
where possible. Reviewable structural equivalence is more important than making the code \
more idiomatic when those goals conflict.

Rules:
- Preserve the same method names (converted to snake_case), field names, and class structure
- Preserve class, method, field, and statement ordering from the Java source
- Preserve the Java control-flow shape; do not rewrite algorithms or collapse explicit
  Java statements into clever Python one-liners
- Emit Python type annotations (PEP 484/585) that match the Java types
- Replace Java idioms with idiomatic Python equivalents:
    * null → None, true/false → True/False
    * this → self
    * List<T> → list[T], Map<K,V> → dict[K, V], Optional<T> → T | None
    * .length() → len(), .size() → len(), .isEmpty() → not x
    * for (T item : collection) → for item in collection:
    * System.out.println → print
    * Math.abs/max/min → abs/max/min (built-in)
- For method overloads: use @typing.overload stubs plus a unified implementation.
  When overloads are dispatched through *args, make the overload stubs positional-only
  with "/" so mypy does not require keyword-call compatibility that Java does not have.
  The concrete implementation must accept every overload signature under mypy.
- Do NOT import unresolved Java platform/framework packages such as javax.*, org.*,
  jakarta.*, or Spring classes as if they were Python modules. When such types are needed
  only for annotations or placeholders, use a local TODO(j2py) stub, a Protocol-shaped
  placeholder, or Any with an explicit TODO comment. Do not add unused type-ignore
  comments for imports that mypy already ignores.
- Never wrap unresolved Java imports in try/except ImportError fallbacks. Generate the
  local placeholder directly instead. Avoid # type: ignore in generated output unless
  there is no typed alternative; fix the type shape instead of suppressing validation.
- When an unresolved Java type appears in overload signatures, prefer a local nominal
  placeholder class or Protocol over Any/object so overload signatures remain distinct.
  Do not emit @overload stubs where an earlier Any/object signature makes a later
  signature unreachable under mypy; either use nominal placeholders or collapse to a
  single implementation signature.
- If same-arity Java overloads would map to overlapping Python signatures, such as
  Object and String becoming object and str, merge those overloads into one Python
  overload using a union of the actually supported runtime types, for example
  `name: ObjectName | str, /`. Never emit an object/Any overload stub that overlaps
  a narrower overload stub of the same arity.
"""
    "- For synchronized(this): initialize self._j2py_lock = threading.Lock() in "
    "__init__ and use with self._j2py_lock\n"
    "- For synchronized(expr) where expr is not this: emit "
    "`from j2py_runtime import _j2py_monitor` when needed and use "
    "`with _j2py_monitor(<expr>):`; do not emit `with <expr>:` for Java monitors. "
    "Keep a # TODO(j2py) or review comment if monitor semantics need human verification.\n"
    """\
- Mark anything you are uncertain about with: # TODO(j2py): <reason>
- Do NOT add docstrings unless the Java had Javadoc
- Keep comments that were in the Java source
- Keep existing # TODO(j2py) markers unless you can complete them correctly from the Java
- Prefer completing unresolved TODO regions from the partial translation instead of
  rewriting already-correct rule-generated code.
- Do NOT invent framework behavior for Spring, Hibernate, reflection, bytecode,
  native/JNI calls, or dependency injection; flag uncertain behavior with # TODO(j2py)
- Output ONLY the Python source code — no explanation, no markdown fences
"""
)

REVIEW_SYSTEM_PROMPT = """\
You are reviewing Java-to-Python translation output for migration risk. Your task is to
find likely semantic mismatches, framework/API boundary assumptions, behavior that a human
reviewer should verify, and maintainability risks that syntax, lint, and type checks may
not catch.

Rules:
- Do not rewrite the Python output.
- Do not mark style preferences as findings unless they affect reviewability or behavior.
- Be conservative: report concrete, checkable risks only.
- Keep findings distinct from rule-layer TODOs unless the TODO points to a real manual
  verification risk.
- Output only JSON with this shape:
  {"findings":[{"severity":"info|warning|error","category":"...","source_line":1|null,
  "output_line":1|null,"message":"...","recommendation":"..."|null}]}
- If there are no findings, output {"findings":[]}.
"""


ADVICE_SYSTEM_PROMPT = """You are an experienced migration planner for Java-to-Python projects.

Task:
- Propose a practical migration plan from this doctor evidence.
- Identify issue slices that should be handled first.
- Recommend concrete config and rule-layer work that this evidence supports.

Hard constraints:
- Use only the evidence object below. Do not add facts not present there.
- If evidence is incomplete for a claim, say "insufficient evidence" and lower confidence.
- Include evidence references explicitly using the format "[evidence: <path>]".
- Keep output as plain markdown with short, reviewable bullets.
- Keep phrasing factual and non-prescriptive.
"""


def build_translation_prompt(
    *,
    java_source: str,
    partial_python: str,
    context: str = "",
    diagnostics: str = "",
    validation_feedback: str = "",
    previous_python: str = "",
) -> tuple[list[TextPromptBlock], list[dict[str, Any]]]:
    """Build the system prompt and messages list for a translation call.

    Returns:
        (system_prompt_blocks, messages) ready for provider-specific client adapters.
    """
    system: list[TextPromptBlock] = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    user_parts: list[str] = []

    if context:
        user_parts.append(f"<project_context>\n{context}\n</project_context>")
    if diagnostics:
        user_parts.append(f"<rule_diagnostics>\n{diagnostics}\n</rule_diagnostics>")
    if validation_feedback:
        user_parts.append(
            f"<validation_feedback>\n{validation_feedback}\n</validation_feedback>",
        )
    if previous_python.strip():
        user_parts.append(
            f"<previous_llm_output>\n{previous_python}\n</previous_llm_output>\n\n"
            "The previous LLM output above failed validation or structural checks. "
            "Repair that Python output using the validation feedback. Preserve correct "
            "logic from the previous output and change only what is needed to produce "
            "valid, reviewable Python."
        )

    user_parts.append(f"<java_source>\n{java_source}\n</java_source>")

    if partial_python.strip():
        user_parts.append(
            f"<partial_translation>\n{partial_python}\n</partial_translation>\n\n"
            "The partial translation above was produced by the rule-based layer. "
            "Complete and correct it to produce reviewable, fully working Python "
            "that preserves the Java structure."
        )
    else:
        user_parts.append("Translate the Java source above to Python.")

    messages = [{"role": "user", "content": "\n\n".join(user_parts)}]
    return system, messages


def build_review_prompt(
    *,
    java_source: str,
    python_source: str,
    context: str = "",
    diagnostics: str = "",
    validation_summary: str = "",
    structural_summary: str = "",
    source_path: str = "",
    output_path: str = "",
) -> tuple[list[TextPromptBlock], list[dict[str, Any]]]:
    """Build the system prompt and messages list for a non-mutating review call."""
    system: list[TextPromptBlock] = [
        {
            "type": "text",
            "text": REVIEW_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    user_parts: list[str] = []
    if source_path:
        user_parts.append(f"<source_path>{source_path}</source_path>")
    if output_path:
        user_parts.append(f"<output_path>{output_path}</output_path>")
    if context:
        user_parts.append(f"<project_context>\n{context}\n</project_context>")
    if diagnostics:
        user_parts.append(f"<rule_diagnostics>\n{diagnostics}\n</rule_diagnostics>")
    if validation_summary:
        user_parts.append(f"<validation_summary>\n{validation_summary}\n</validation_summary>")
    if structural_summary:
        user_parts.append(f"<structural_summary>\n{structural_summary}\n</structural_summary>")
    user_parts.append(f"<java_source>\n{java_source}\n</java_source>")
    user_parts.append(f"<python_output>\n{python_source}\n</python_output>")
    user_parts.append("Review the Java and Python above. Return only the structured JSON findings.")
    return system, [{"role": "user", "content": "\n\n".join(user_parts)}]


def build_doctor_advice_prompt(
    *,
    evidence_json: str,
) -> tuple[list[TextPromptBlock], list[dict[str, Any]]]:
    """Build the system prompt and messages list for an advice call."""
    system: list[TextPromptBlock] = [
        {
            "type": "text",
            "text": ADVICE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    user_parts = [
        "Use this evidence object only. Do not invent facts.",
        "<evidence>",
        evidence_json,
        "</evidence>",
        (
            "Return markdown with these headings:\n"
            "## Migration plan\n## Issue slices\n## Config and rule-work"
        ),
        "Include explicit evidence tags in each section as [evidence: <path>].",
    ]
    return system, [{"role": "user", "content": "\n\n".join(user_parts)}]
