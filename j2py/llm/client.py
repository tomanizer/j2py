"""Anthropic API client with caching and retry logic."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import anthropic
import diskcache
from anthropic.types import TextBlockParam
from tenacity import retry, stop_after_attempt, wait_exponential

from j2py.llm.prompts import PROMPT_VERSION

_CACHE_DIR = Path.home() / ".cache" / "j2py" / "llm"
_cache = diskcache.Cache(str(_CACHE_DIR))

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for LLM translation")
    if _client is None:
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _cache_key(
    *,
    model: str,
    java_source: str,
    partial_python: str,
    context: str,
    diagnostics: str,
    validation_feedback: str,
    previous_python: str,
    config_fingerprint: str,
    system: str,
) -> str:
    payload = json.dumps(
        {
            "config_fingerprint": config_fingerprint,
            "context": context,
            "diagnostics": diagnostics,
            "java_sha256": hashlib.sha256(java_source.encode()).hexdigest(),
            "model": model,
            "partial_sha256": hashlib.sha256(partial_python.encode()).hexdigest(),
            "previous_sha256": hashlib.sha256(previous_python.encode()).hexdigest(),
            "prompt_version": PROMPT_VERSION,
            "system": system,
            "validation_feedback": validation_feedback,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _system_text(system: list[TextBlockParam]) -> str:
    texts: list[str] = []
    for block in system:
        text = block.get("text")
        if block.get("type") == "text" and isinstance(text, str):
            texts.append(text)
    return "\n".join(texts)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def translate_with_llm(
    *,
    java_source: str,
    partial_python: str,
    context: str = "",
    diagnostics: str = "",
    validation_feedback: str = "",
    previous_python: str = "",
    config_fingerprint: str = "",
    model: str = "claude-sonnet-4-6",
    use_cache: bool = True,
) -> str:
    """Send a Java class + its partial skeleton to Claude for completion.

    Args:
        java_source: Original Java source (the full class).
        partial_python: The rule-translated skeleton (may be partial/incomplete).
        context: Optional project context (class hierarchy, imports, etc.).
        model: Claude model ID to use.
        use_cache: Whether to use the disk cache (disable for re-translation).

    Returns:
        Complete Python source for the class.
    """
    from j2py.llm.prompts import build_translation_prompt

    system, messages = build_translation_prompt(
        java_source=java_source,
        partial_python=partial_python,
        context=context,
        diagnostics=diagnostics,
        validation_feedback=validation_feedback,
        previous_python=previous_python,
    )

    key = _cache_key(
        model=model,
        java_source=java_source,
        partial_python=partial_python,
        context=context,
        diagnostics=diagnostics,
        validation_feedback=validation_feedback,
        previous_python=previous_python,
        config_fingerprint=config_fingerprint,
        system=_system_text(system),
    )
    if use_cache:
        cached: str | None = _cache.get(key)
        if cached is not None:
            return cached

    response = get_client().messages.create(
        model=model,
        max_tokens=8192,
        system=system,
        messages=messages,  # type: ignore[arg-type]
    )

    first_block = response.content[0]
    if not isinstance(first_block, anthropic.types.TextBlock):
        raise RuntimeError(f"Unexpected response block type: {type(first_block)}")
    result = _strip_fences(first_block.text)

    if use_cache:
        _cache[key] = result

    return result


def _strip_fences(text: str) -> str:
    """Strip markdown code fences Claude sometimes adds despite being asked not to."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop opening fence line (```python, ```py, or plain ```)
        start = 1
        # find closing fence
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        return "\n".join(lines[start:end]) + "\n"
    return text
