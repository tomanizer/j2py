"""LLM API clients with caching and retry logic."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Literal, Protocol, cast

import anthropic
import diskcache
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from j2py.dotenv import load_repo_dotenv
from j2py.llm.prompts import PROMPT_VERSION, TextPromptBlock

_CACHE_DIR = Path.home() / ".cache" / "j2py" / "llm"
_cache = diskcache.Cache(str(_CACHE_DIR))

# Output token ceiling for a single class translation. 8192 was too low for large
# classes (silent truncation, see LLMTruncationError). 32K is well within the 64K
# streamable limit of the default Anthropic model. Values this large require
# streaming — a non-streaming request would trip the SDK's >10-minute timeout guard.
MAX_OUTPUT_TOKENS = 32000
GEMINI_EXTRA_INSTALL_HINT = 'pip install "j2py-converter[gemini]"'


class GeminiModels(Protocol):
    def generate_content_stream(self, **kwargs: object) -> Iterator[object]: ...


class GeminiClient(Protocol):
    models: GeminiModels


_client: anthropic.Anthropic | None = None
_gemini_client: GeminiClient | None = None

LLMProvider = Literal["anthropic", "gemini"]
DEFAULT_MODELS: dict[LLMProvider, str] = {
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-3.5-flash",
}


class LLMTruncationError(RuntimeError):
    """Raised when the model stopped at ``max_tokens`` — the completion is incomplete.

    Retrying does not help (the same oversized class deterministically overruns the budget),
    so this is excluded from the tenacity retry policy. The class must be split or sent in
    smaller units. The truncated text is never cached.
    """


class MissingGeminiExtraError(RuntimeError):
    """Raised when Gemini is selected without installing the optional SDK extra."""


def get_client() -> anthropic.Anthropic:
    global _client
    load_repo_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for LLM translation")
    if _client is None:
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def gemini_api_key_problem(key: str | None) -> str | None:
    """Return a human hint when ``key`` looks like the wrong credential type."""
    if not key or not key.strip():
        return "GEMINI_API_KEY is not set"
    stripped = key.strip()
    if stripped.startswith("ya29."):
        return (
            "GEMINI_API_KEY looks like a gcloud OAuth access token (ya29...), "
            "not a Google AI Studio API key"
        )
    if stripped.startswith("Bearer "):
        return "GEMINI_API_KEY must be the raw key value, not a Bearer header"
    return None


def _missing_gemini_extra_error() -> RuntimeError:
    return MissingGeminiExtraError(
        "Gemini LLM provider requires the optional Gemini extra. "
        f"Install it with: {GEMINI_EXTRA_INSTALL_HINT}"
    )


def _import_google_genai() -> Any:
    try:
        from google import genai
    except ImportError as exc:
        if exc.name in {"google", "google.genai"}:
            raise _missing_gemini_extra_error() from None
        raise
    return genai


def _import_google_genai_types() -> Any:
    try:
        from google.genai import types
    except ImportError as exc:
        if exc.name in {"google", "google.genai"}:
            raise _missing_gemini_extra_error() from None
        raise
    return types


def get_gemini_client() -> GeminiClient:
    global _gemini_client
    load_repo_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    problem = gemini_api_key_problem(api_key)
    if problem:
        raise RuntimeError(f"{problem}. Create a key at https://aistudio.google.com/apikey.")
    if _gemini_client is None:
        genai = _import_google_genai()
        _gemini_client = cast(GeminiClient, genai.Client(api_key=api_key))
    return _gemini_client


def resolve_model(provider: LLMProvider, model: str | None) -> str:
    return model or DEFAULT_MODELS[provider]


def _cache_key(
    *,
    provider: LLMProvider,
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
            "provider": provider,
            "prompt_version": PROMPT_VERSION,
            "system": system,
            "validation_feedback": validation_feedback,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _system_text(system: list[TextPromptBlock]) -> str:
    texts: list[str] = []
    for block in system:
        text = block.get("text")
        if block.get("type") == "text" and isinstance(text, str):
            texts.append(text)
    return "\n".join(texts)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_not_exception_type((LLMTruncationError, MissingGeminiExtraError)),
)
def translate_with_llm(
    *,
    java_source: str,
    partial_python: str,
    context: str = "",
    diagnostics: str = "",
    validation_feedback: str = "",
    previous_python: str = "",
    config_fingerprint: str = "",
    model: str | None = None,
    provider: LLMProvider = "anthropic",
    use_cache: bool = True,
) -> str:
    """Send a Java class + its partial skeleton to the configured LLM for completion.

    Args:
        java_source: Original Java source (the full class).
        partial_python: The rule-translated skeleton (may be partial/incomplete).
        context: Optional project context (class hierarchy, imports, etc.).
        model: Model ID to use. Defaults depend on ``provider``.
        provider: LLM provider to call.
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
    resolved_model = resolve_model(provider, model)

    key = _cache_key(
        provider=provider,
        model=resolved_model,
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
            if provider == "gemini":
                from j2py.llm.usage import record_gemini_cache_hit

                record_gemini_cache_hit(model=resolved_model)
            return cached

    if provider == "anthropic":
        result = _translate_with_anthropic(
            model=resolved_model,
            system=system,
            messages=messages,
        )
    elif provider == "gemini":
        result = _translate_with_gemini(
            model=resolved_model,
            system_text=_system_text(system),
            contents=_message_text(messages),
        )
    else:  # pragma: no cover - Literal prevents this for typed callers
        raise ValueError(f"Unsupported LLM provider: {provider}")

    if use_cache:
        _cache[key] = result

    return result


def _translate_with_anthropic(
    *,
    model: str,
    system: list[TextPromptBlock],
    messages: list[dict[str, object]],
) -> str:
    # Stream the response: at MAX_OUTPUT_TOKENS the SDK refuses a non-streaming
    # request (estimated >10 min → ValueError). get_final_message() still yields the
    # full Message, including stop_reason, once the stream completes.
    with get_client().messages.stream(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=cast(Iterable[anthropic.types.TextBlockParam], system),
        messages=messages,  # type: ignore[arg-type]
    ) as stream:
        response = stream.get_final_message()

    if getattr(response, "stop_reason", None) == "max_tokens":
        raise LLMTruncationError(
            "LLM response hit the max_tokens limit; the translation is truncated and "
            "would emit broken Python. Split the class into smaller units before retrying."
        )

    first_block = response.content[0]
    if not isinstance(first_block, anthropic.types.TextBlock):
        raise RuntimeError(f"Unexpected response block type: {type(first_block)}")
    return _strip_fences(first_block.text)


def _translate_with_gemini(*, model: str, system_text: str, contents: str) -> str:
    types = _import_google_genai_types()
    client = get_gemini_client()
    # Use the streaming endpoint for parity with Anthropic at the 32K output-token
    # budget. Large class translations can run long enough that one-shot provider calls
    # are more likely to hit SDK/client timeout guards, while the streaming response still
    # exposes chunk text and final finish reasons for truncation detection.
    chunks = client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS,
            system_instruction=system_text,
        ),
    )
    parts: list[str] = []
    last_chunk: object | None = None
    for chunk in chunks:
        last_chunk = chunk
        if _gemini_hit_max_tokens(chunk):
            raise LLMTruncationError(
                "Gemini response hit the max_output_tokens limit; the translation is "
                "truncated and would emit broken Python. Split the class into smaller "
                "units before retrying."
            )
        text = getattr(chunk, "text", None)
        if isinstance(text, str):
            parts.append(text)
    if not parts:
        raise RuntimeError("Gemini response did not include text output")
    from j2py.llm.usage import record_gemini_api_usage

    if last_chunk is not None:
        record_gemini_api_usage(model=model, response=last_chunk)
    return _strip_fences("".join(parts))


def _message_text(messages: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
    return "\n\n".join(parts)


def _gemini_hit_max_tokens(response: object) -> bool:
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return False
    first = candidates[0]
    reason = getattr(first, "finish_reason", None)
    reason_name = getattr(reason, "name", None)
    reason_text = reason_name if isinstance(reason_name, str) else str(reason)
    return reason_text.upper().endswith("MAX_TOKENS")


def _strip_fences(text: str) -> str:
    """Strip markdown code fences LLMs sometimes add despite being asked not to."""
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
