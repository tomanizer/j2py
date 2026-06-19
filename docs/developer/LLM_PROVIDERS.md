# LLM Providers

Use this guide when changing LLM provider calls, prompts, cache behavior, retry behavior,
or live-test boundaries.

j2py's default quality bar is deterministic rule-layer translation. LLM completion is an
optional second stage for code the rule layer cannot finish.

## Ownership

| Area | Module | Tests |
|------|--------|-------|
| Provider clients, cache keys, retries | `j2py/llm/client.py` | `tests/llm/`, `tests/cli/test_main.py` |
| Prompt construction | `j2py/llm/prompts.py` | `tests/llm/` |
| LLM review parsing | `j2py/llm/review.py` | `tests/llm/` |
| Harvest support | `j2py/llm/harvest.py` | `tests/harvest/`, `docs/LLM_HARVEST.md` |
| Usage accounting | `j2py/llm/usage.py` | `tests/llm/` |
| Pipeline integration | `j2py/pipeline.py` | `tests/test_pipeline.py`, CLI tests |

## Provider Contract

Provider changes must preserve:

- no live LLM calls during `make check`;
- cache keys partitioned by provider, model, endpoint, prompt version, config
  fingerprint, source, partial output, diagnostics, and feedback;
- truncated completions are not cached;
- missing optional provider extras fail with actionable install hints;
- OpenAI-compatible providers require an explicit model;
- validation feedback is sanitized before it affects LLM cache keys.

The supported provider literal currently lives in `j2py/llm/client.py` as `LLMProvider`.
Changing it usually also means updating CLI choices, config docs, API reference, install
extras, and tests.

## Prompt Changes

Prompt changes can alter generated output across many fixtures. When changing prompts:

- bump the relevant prompt version in `j2py/llm/prompts.py`;
- update tests that assert prompt content;
- avoid adding project secrets or absolute local paths to prompts;
- keep structural-correspondence instructions prominent;
- explain new prompt behavior in docs if user-visible.

Prompt changes should not be used to compensate for deterministic rule gaps that can be
fixed in the rule layer.

## Cache And Retry Rules

`translate_with_llm(...)` and `review_translation_with_llm(...)` use diskcache and tenacity
retries. Cache keys must change when any input that can affect output changes. Retrying
should exclude deterministic non-retryable failures such as truncation and missing extras.

If adding a provider endpoint option, include endpoint identity in the cache key. This is
required so OpenAI-compatible providers do not share cached answers for different servers.

## Live Tests

Normal tests must not call provider APIs. Live tests belong behind explicit markers and
manual commands only.

Expected boundaries:

- `make check` excludes `live_llm`;
- `tests/llm/test_e2e_llm.py` is marked `live_llm`;
- live provider tests require the relevant API key;
- docs and CLI errors should explain missing keys or extras clearly.

Run regular provider tests:

```bash
pytest tests/llm tests/cli/test_main.py -q
```

Run live tests only when explicitly requested and credentials are available:

```bash
pytest -m live_llm tests/llm/test_e2e_llm.py -q
make test-llm-e2e
make test-llm-gemini-e2e
```

## Review Checklist

- No default test path can call a live provider.
- Cache keys cover every output-affecting input.
- Prompt-version changes are intentional and documented.
- Optional extras fail with actionable messages.
- CLI, config, API reference, and install docs still agree.
