# j2py — Agent guidance (Codex, Copilot, Cursor, and others)

This file mirrors [CLAUDE.md](CLAUDE.md) for non-Claude agents. Both must be kept in sync.

## Mission

j2py converts Java source to semantically equivalent Python with line-level structural
correspondence. "Working Python" is necessary but not sufficient — the output must be
reviewable against the original Java side-by-side.

## Before writing any code

Read these documents first:

- [docs/PRD.md](docs/PRD.md) — product goals and non-goals
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — pipeline stages and component boundaries
- [docs/decisions/](docs/decisions/) — settled design decisions as ADRs
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow, commit style, PR rules

## Pipeline summary

| Stage | Package | Status |
|---|---|---|
| Java parsing | `j2py/parse/` | Implemented |
| Symbol analysis | `j2py/analyze/` | Implemented |
| Rule-based skeleton | `j2py/translate/skeleton.py` | Implemented but incomplete |
| Direct visitors | `j2py/translate/classes.py`, `statements.py`, `expressions.py` | Implemented |
| Type/naming/literal rules | `j2py/translate/rules/` | Implemented |
| LLM completion | `j2py/llm/` | Implemented |
| Validation | `j2py/validate/` | Implemented |
| CLI | `j2py/cli/` | Implemented |

## Constraints — do not violate without an ADR

- Parser: **tree-sitter-java only** — do not introduce javalang, ANTLR, or regex-based parsing
- LLM: **Anthropic SDK only** — no LangChain, no OpenAI, no litellm wrappers
- Output target: **Python 3.11+** with PEP 484/585 type annotations
- Tests: **no live Anthropic API calls in the normal test suite or CI**.
  The single exception is the on-demand exploratory test
  `tests/llm/test_e2e_llm.py` (marked `live_llm`). It is excluded by default
  via pytest configuration (`addopts = ... -m 'not live_llm'`). It may only be run
  explicitly with `pytest -m live_llm ...` (after setting `ANTHROPIC_API_KEY`)
  when a human wants to manually evaluate the current tree-sitter + rule
  skeleton quality against real LLM completion. This test must never be
  required for `make check` or PRs.
- Rule layer: keep deterministic helpers focused and stateless where possible; use
  `TranslationContext` and diagnostics when a rule cannot preserve Java semantics

## Quality gates

Every PR must pass:

```bash
make check     # lint (ruff) + typecheck (mypy strict) + test (pytest)
```

Note: `make check` (and normal `pytest`) deliberately exclude the `live_llm`
marker. The one exploratory live-LLM test can only be run on demand (see
constraints above).

CI runs the same checks. A red CI means `make check` was skipped.

## New translation rules

Add to `j2py/translate/classes.py`, `statements.py`, `expressions.py`, or pure helpers
under `j2py/translate/rules/`. Each rule needs:
1. A Java fixture in `tests/fixtures/java/`
2. An expected Python fixture in `tests/fixtures/python/`
3. A parametrised test in `tests/translate/`

## When to create an ADR

Any change to: parser library, LLM provider, pipeline stages, Python output version,
or non-obvious translation choices (e.g., how to handle Java method overloading).
See [ADR 0001](docs/decisions/0001-record-architecture-decisions.md) for the template.
