"""Structured prompts for LLM-assisted Java→Python translation."""

from __future__ import annotations

from typing import Any

from anthropic.types import TextBlockParam

PROMPT_VERSION = "j2py-translation-v7"

SYSTEM_PROMPT = """\
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
- For synchronized(this): initialize self._j2py_lock = threading.Lock() in __init__ \
and use with self._j2py_lock
- For other synchronized locks: use with <expr> and verify the monitor supports \
context management
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


def build_translation_prompt(
    *,
    java_source: str,
    partial_python: str,
    context: str = "",
    diagnostics: str = "",
    validation_feedback: str = "",
    previous_python: str = "",
) -> tuple[list[TextBlockParam], list[dict[str, Any]]]:
    """Build the system prompt and messages list for a translation call.

    Returns:
        (system_prompt_blocks, messages) ready for the Anthropic messages API.
    """
    system: list[TextBlockParam] = [
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
