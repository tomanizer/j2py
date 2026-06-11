"""Structured prompts for LLM-assisted Java→Python translation."""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "j2py-translation-v2"

SYSTEM_PROMPT = """\
You are an expert Java-to-Python translator. Your goal is to produce Python code that is \
semantically and functionally equivalent to the input Java, with line-level structural \
correspondence where possible.

Rules:
- Preserve the same method names (converted to snake_case), field names, and class structure
- Emit Python type annotations (PEP 484/585) that match the Java types
- Replace Java idioms with idiomatic Python equivalents:
    * null → None, true/false → True/False
    * this → self
    * List<T> → list[T], Map<K,V> → dict[K, V], Optional<T> → T | None
    * .length() → len(), .size() → len(), .isEmpty() → not x
    * for (T item : collection) → for item in collection:
    * System.out.println → print
    * Math.abs/max/min → abs/max/min (built-in)
- For method overloads: use @typing.overload stubs + a unified implementation
- For synchronized(this): initialize self._j2py_lock = threading.Lock() in __init__ \
and use with self._j2py_lock
- For other synchronized locks: use with <expr> and verify the monitor supports \
context management
- Mark anything you are uncertain about with: # TODO(j2py): <reason>
- Do NOT add docstrings unless the Java had Javadoc
- Keep comments that were in the Java source
- Prefer completing unresolved TODO regions from the partial translation instead of
  rewriting already-correct rule-generated code.
- Output ONLY the Python source code — no explanation, no markdown fences
"""


def build_translation_prompt(
    *,
    java_source: str,
    partial_python: str,
    context: str = "",
    diagnostics: str = "",
    validation_feedback: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """Build the system prompt and messages list for a translation call.

    Returns:
        (system_prompt, messages) ready for the Anthropic messages API.
    """
    user_parts: list[str] = []

    if context:
        user_parts.append(f"<project_context>\n{context}\n</project_context>")
    if diagnostics:
        user_parts.append(f"<rule_diagnostics>\n{diagnostics}\n</rule_diagnostics>")
    if validation_feedback:
        user_parts.append(
            f"<validation_feedback>\n{validation_feedback}\n</validation_feedback>",
        )

    user_parts.append(f"<java_source>\n{java_source}\n</java_source>")

    if partial_python.strip():
        user_parts.append(
            f"<partial_translation>\n{partial_python}\n</partial_translation>\n\n"
            "The partial translation above was produced by the rule-based layer. "
            "Complete and correct it to produce idiomatic, fully working Python."
        )
    else:
        user_parts.append("Translate the Java source above to Python.")

    messages = [{"role": "user", "content": "\n\n".join(user_parts)}]
    return SYSTEM_PROMPT, messages
