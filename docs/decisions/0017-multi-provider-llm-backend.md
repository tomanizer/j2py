# ADR 0017 — Multi-provider LLM backend

**Date:** 2026-06-15
**Status:** Accepted

## Context

ADR 0004 selected Claude through the Anthropic SDK as the only LLM backend. That kept the
first implementation simple, but the CLI and pipeline now need to support Gemini Flash for
users who have a `GEMINI_API_KEY` and want to run the same rule-layer completion workflow
without an Anthropic key.

The LLM layer still needs provider-specific API behavior: system instructions, output
token limits, response-shape checks, retry semantics, and cache key stability are part of
the translation contract.

## Decision

Support explicit LLM provider selection:

- Default provider: `anthropic`
- Optional provider: `gemini`
- Default Anthropic model: `claude-sonnet-4-6`
- Default Gemini model: `gemini-3.5-flash`

Use each provider's official SDK directly:

- Anthropic via `anthropic`
- Gemini via `google-genai`

Do not introduce a provider abstraction framework such as LangChain or litellm. Keep a
small in-repo dispatcher in `j2py.llm.client.translate_with_llm(...)` and keep the pipeline
contract provider-neutral.

Cache keys must include the provider and resolved model. Live provider tests remain
excluded from normal CI; default tests use stubs/fakes.

## Consequences

+ Users can run LLM completion with either `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`.
+ Anthropic remains the default, so existing invocations keep their behavior.
+ Direct SDK calls preserve provider-specific prompt and response handling.
− The LLM client owns a small amount of provider branching.
− Prompt-cache behavior remains Anthropic-specific unless a provider exposes equivalent
  semantics later.

## References

- [ADR 0004](0004-claude-as-llm-backend.md) — original single-provider backend decision
- Anthropic SDK: https://github.com/anthropics/anthropic-sdk-python
- Gemini text generation docs: https://ai.google.dev/gemini-api/docs/text-generation
- Gemini API key docs: https://ai.google.dev/gemini-api/docs/api-key
