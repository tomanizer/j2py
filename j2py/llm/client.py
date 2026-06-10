"""Anthropic API client with caching and retry logic."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import anthropic
import diskcache
from tenacity import retry, stop_after_attempt, wait_exponential


_CACHE_DIR = Path.home() / ".cache" / "j2py" / "llm"
_cache = diskcache.Cache(str(_CACHE_DIR))

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def _cache_key(model: str, messages: list[dict[str, Any]], system: str) -> str:
    payload = json.dumps({"model": model, "messages": messages, "system": system}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def translate_with_llm(
    *,
    java_source: str,
    partial_python: str,
    context: str = "",
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
    )

    if use_cache:
        key = _cache_key(model, messages, system)
        if key in _cache:
            return _cache[key]  # type: ignore[return-value]

    response = get_client().messages.create(
        model=model,
        max_tokens=8192,
        system=system,
        messages=messages,  # type: ignore[arg-type]
    )

    result = response.content[0].text

    if use_cache:
        _cache[key] = result

    return result
