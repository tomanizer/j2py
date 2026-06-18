# ADR 0017 — Multi-provider LLM backend

**Date:** 2026-06-15
**Status:** Accepted

## Context

ADR 0004 selected Claude through the Anthropic SDK as the only LLM backend. That kept the
first implementation simple, but the CLI and pipeline now need to support additional
providers for users who want to run the same rule-layer completion workflow without an
Anthropic key. Gemini Flash covers the Google-hosted path. OpenAI-compatible endpoints
cover providers, gateways, and self-hosted deployments that expose the OpenAI chat
completion API shape.

The LLM layer still needs provider-specific API behavior: system instructions, output
token limits, response-shape checks, retry semantics, and cache key stability are part of
the translation contract.

## Decision

Support explicit LLM provider selection:

- Default provider: `anthropic`
- Optional provider: `gemini`
- Optional provider: `openai` for OpenAI-compatible chat-completion endpoints
- Default Anthropic model: `claude-sonnet-4-6`
- Default Gemini model: `gemini-3.5-flash`
- No default OpenAI-compatible model; endpoint model IDs are deployment-specific and must
  be passed explicitly

Use each provider's official SDK directly:

- Anthropic via `anthropic`
- Gemini via `google-genai`
- OpenAI-compatible endpoints via `openai`

Both provider paths use streaming for high-token completions. Anthropic requires
streaming at j2py's 32K output-token ceiling because the SDK can reject long
non-streaming requests with timeout-guard errors. Gemini has not shown the same
failure in normal use yet, but `google-genai` exposes `models.generate_content_stream`,
so j2py uses that path for parity and to avoid one-shot large-completion timeout risk.
Streaming responses are still assembled into the same plain Python string before cache
writeback, and `MAX_TOKENS` / `max_output_tokens` finish reasons still raise
`LLMTruncationError`.

OpenAI-compatible endpoints use non-streaming `chat.completions.create(...)` with
system/user messages and the shared output-token ceiling. The endpoint can come from the
explicit `llm_base_url` config/CLI value or from `OPENAI_BASE_URL`; the default endpoint
identity is `https://api.openai.com/v1`. The provider accepts `openai-compatible` as a
compatibility alias but normalizes it to `openai`.

Do not introduce a provider abstraction framework such as LangChain or litellm. Keep a
small in-repo dispatcher in `j2py.llm.client.translate_with_llm(...)` and keep the pipeline
contract provider-neutral.

Cache keys must include the provider, provider endpoint identity, and resolved model. Live
provider tests remain excluded from normal CI; default tests use stubs/fakes.

## Consequences

+ Users can run LLM completion with `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or
  `OPENAI_API_KEY`.
+ Anthropic remains the default, so existing invocations keep their behavior.
+ Direct SDK calls preserve provider-specific prompt and response handling.
− The LLM client owns a small amount of provider branching.
− Prompt-cache behavior remains Anthropic-specific unless a provider exposes equivalent
  semantics later.
− OpenAI-compatible provider users must know the correct endpoint model ID up front.

## References

- [ADR 0004](0004-claude-as-llm-backend.md) — original single-provider backend decision
- Anthropic SDK: https://github.com/anthropics/anthropic-sdk-python
- Gemini text generation docs: https://ai.google.dev/gemini-api/docs/text-generation
- Gemini API key docs: https://ai.google.dev/gemini-api/docs/api-key
- OpenAI Python SDK: https://github.com/openai/openai-python
