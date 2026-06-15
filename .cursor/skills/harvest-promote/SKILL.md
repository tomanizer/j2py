---
name: harvest-promote
description: >-
  Run the j2py LLM harvest promotion pipeline: build/refresh Tier A queue,
  Gemini batch harvest (with content cache), prune, triage, and draft or create
  pattern-family GitHub issues from top repair signals. Use when promoting harvest
  findings to rule-layer work, refreshing the harvest queue, or filing harvest issues.
disable-model-invocation: true
---

# Harvest promote pipeline

Automates: **queue → local probes → Gemini harvest → prune → triage → pattern-family GitHub issues**.

Read first: [docs/LLM_HARVEST.md](../../../docs/LLM_HARVEST.md).

## When to use

- User asks to run harvest promotion, refresh harvest queue, or file issues from triage
- After corpus scans (`corpus-reports/*.json`) need to flow into LLM harvest
- `make harvest-triage` showed new repair signals to promote
- User wants pattern-family GitHub issues (not single-file point fixes)

## Prerequisites

- `GEMINI_API_KEY` in checkout `.env` or `$J2PY_CORPUS_ROOT/.env`
- For queue build: `corpus-reports/*.json` from corpus scans (Tier A sources)
- For `--create-issues`: `gh` CLI authenticated
- **Worktrees:** `export J2PY_CORPUS_ROOT=/path/to/main/j2py` so `.env`, `.j2py/harvest/`,
  and `.corpus/` resolve from the main checkout

## Commands

| Goal | Command |
|------|---------|
| Dry run (no LLM) | `make harvest-promote-dry ISSUES=3` |
| Full pipeline (draft issues) | `make harvest-promote LIMIT=2 ISSUES=3` |
| Create GitHub issues | `make harvest-promote-issues` |
| Queue only | `make harvest-queue` |
| Force queue rebuild | `make harvest-queue REFRESH=1` |
| Triage only | `make harvest-triage` |
| Local probes only | `make harvest-pipeline` |
| Manual batch harvest | `make harvest-gemini OFFSET=0 LIMIT=10` |

Makefile variables: `LIMIT` (Gemini files per promote run, default `2`), `ISSUES`
(pattern issues per run, default `3`), `OFFSET` / `SLEEP` / `FILE_LIST` for
`harvest-gemini`.

Direct script:

```bash
uv run python scripts/harvest/run_harvest_promotion.py \
  --limit 2 --issues 3                    # draft
uv run python scripts/harvest/run_harvest_promotion.py --create-issues
uv run python scripts/harvest/run_harvest_promotion.py \
  --skip-harvest --skip-local --issues 3  # dry (same as make harvest-promote-dry)
```

Force re-harvest (ignore content cache):

```bash
uv run python scripts/harvest/run_harvest_promotion.py --force
uv run python scripts/harvest/run_llm_harvest.py --no-skip-cached ...
```

## What the pipeline does

1. **Queue** — Builds `.j2py/harvest/queue.txt` if missing or older than
   `corpus-reports/*.json`. Tier A: `coverage == 1.0`, `syntax_ok == false`,
   `unhandled_count == 0`. Script: `scripts/harvest/build_harvest_queue.py`.
2. **Local harvest** — Runs `tests/fixtures/llm/*.java` (cheap probes).
3. **Gemini batch** — Next slice from queue (`state.harvest_offset`, `LIMIT` files).
   Skips paths cached in `records.jsonl` at same `java_sha256` unless `--force` /
   `--no-skip-cached`.
4. **Prune + triage** — Dedupes `records.jsonl`, prints aggregate report.
5. **Issue promotion** — Top N **pattern families** via
   `scripts/harvest/promote_harvest_signals.py`. Skips signals already in
   `state.filed_signals` or with open GitHub issues matching `harvest: <signal>`.
   Default: draft to stdout; `--create-issues` runs `gh issue create`.

## Pattern-family rules

Issues must **not** anchor on one fixture. The promoter uses:

- [scripts/harvest/signal_patterns.py](../../../scripts/harvest/signal_patterns.py) — pattern metadata, titles, acceptance criteria
- [.github/ISSUE_TEMPLATE/rule-layer-pattern.md](../../../.github/ISSUE_TEMPLATE/rule-layer-pattern.md) — issue shape
- [.github/issue-drafts/harvest-pattern-issue-template.md](../../../.github/issue-drafts/harvest-pattern-issue-template.md) — draft copy

After creating issues, implement **general visitor/registry rules** with parametrised tests.
Wire `FUTURE_TARGETS` with `tracking="issue-NNN"` for coverage-gap patterns.

## Local state (`.j2py/harvest/`, gitignored)

| File | Purpose |
|------|---------|
| `records.jsonl` | Harvest records (one per LLM translation) |
| `usage.jsonl` | Gemini token usage |
| `queue.txt` | Tier-A corpus paths |
| `state.json` | `harvest_offset`, `filed_signals`, promotion timestamps |

Reset queue progress: edit `harvest_offset` in `state.json` or run
`make harvest-queue REFRESH=1`.

## If queue build fails

No `corpus-reports/*.json`: run corpus scan first ([docs/CORPUS_SCOREBOARD.md](../../../docs/CORPUS_SCOREBOARD.md)).

Still can triage and draft from existing records:

```bash
make harvest-promote-dry
uv run python scripts/harvest/run_harvest_promotion.py --skip-harvest --skip-local --issues 3
```

## Verify

```bash
uv run pytest tests/harvest/ -q
make harvest-promote-dry ISSUES=2
cat .j2py/harvest/state.json
```

## Related docs

- [docs/LLM_HARVEST.md](../../../docs/LLM_HARVEST.md) — full operator guide
- [docs/TRANSLATION_TARGETS.md](../../../docs/TRANSLATION_TARGETS.md) — FUTURE_TARGETS workflow
- [docs/decisions/0017-llm-harvest-for-rule-layer-backlog.md](../../../docs/decisions/0017-llm-harvest-for-rule-layer-backlog.md) — ADR
