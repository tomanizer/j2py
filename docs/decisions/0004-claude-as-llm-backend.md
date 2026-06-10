# ADR 0004 — Use Claude (Anthropic SDK) as LLM backend

**Date:** 2026-06-10
**Status:** Accepted

## Context

The LLM layer needs a model capable of:
- Understanding both Java and Python at a high level
- Producing syntactically valid Python with correct type annotations
- Following detailed system prompts about structural conventions
- Handling large class bodies (8k+ output tokens)

Candidate approaches:
- **Anthropic SDK (Claude):** Claude 3.x/4.x family; strong code understanding; the
  project owner already uses Claude Code for development tooling
- **OpenAI SDK (GPT-4o):** comparable code capability; different API; additional
  dependency
- **litellm / LangChain abstraction:** provider-agnostic; adds a dependency layer that
  obscures the actual API semantics and makes prompt debugging harder

## Decision

Use the `anthropic` SDK directly. No abstraction layer.

Default model: `claude-sonnet-4-6` (configurable via `--model` CLI flag and
`TranslationConfig`). This allows upgrading the model without a code change.

**Caching:** disk-cache at `~/.cache/j2py/llm/` keyed on SHA256 of
`(model, system_prompt, messages)`. Unchanged files are never re-translated.

**Retry:** `tenacity` with 3 attempts, exponential back-off (2s–30s).

## Consequences

+ Direct SDK access — no abstraction overhead; full access to system prompt, message
  structure, token counting, and model parameters
+ Model is a runtime parameter — upgrading from `claude-sonnet-4-6` to a future model
  requires no code change, just a config or CLI flag
+ Disk cache makes large-project translation incremental (only changed files re-hit API)
− Requires `ANTHROPIC_API_KEY` in environment; `j2py --no-llm` skips the LLM layer
  entirely for offline/CI use
− Switching LLM providers requires a code change to `llm/client.py`; a new ADR would
  be needed at that point

## References

- Anthropic SDK: https://github.com/anthropics/anthropic-sdk-python
- [ADR 0003](0003-layered-translation-pipeline.md) — LLM is the second pipeline layer
