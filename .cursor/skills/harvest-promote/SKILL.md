---
name: harvest-promote
description: >-
  Run the j2py LLM harvest promotion pipeline: Tier A queue, Gemini batch harvest with
  content cache, prune, triage, pattern-family GitHub issue drafts. Use when promoting
  harvest findings, make harvest-promote-dry, harvest-queue, or filing harvest issues.
  Requires GEMINI_API_KEY for live harvest steps; dry-run needs only records.jsonl.
disable-model-invocation: true
---

# Harvest promote pipeline

**queue → local probes → Gemini harvest → prune → triage → pattern-family GitHub issues**

Live LLM steps cost API quota. Prefer `make harvest-promote-dry` until drafts look right.

Read first: [docs/LLM_HARVEST.md](../../../docs/LLM_HARVEST.md).

## When to use

| Gap | Tool |
|-----|------|
| `coverage < 1.0` / unhandled | [add-translation-rule](../add-translation-rule/SKILL.md) — not harvest |
| `coverage == 1.0`, `syntax_ok == false` | This skill |
| Issues already drafted | `harvest-promote-dry` only |

## Prerequisites

- `GEMINI_API_KEY` in `.env` or `$J2PY_CORPUS_ROOT/.env` (Makefile `LOAD_GEMINI_ENV`)
- Queue build: `corpus-reports/*.json` from [corpus-gap-triage](../corpus-gap-triage/SKILL.md)
- `gh` auth for `make harvest-promote-issues`
- Worktree: `export J2PY_CORPUS_ROOT=/path/to/main/j2py` (`.env`, `.j2py/harvest/`, `.corpus/`)

Invalid keys: OAuth tokens (`ya29.…`) are rejected — use a Gemini API key (`AI…` / `AQ…`).

## Commands

| Goal | Command |
|------|---------|
| Dry run (no LLM) | `make harvest-promote-dry ISSUES=3` |
| Full slice + drafts | `make harvest-promote LIMIT=2 ISSUES=3` |
| Create GitHub issues | `make harvest-promote-issues` |
| Queue only | `make harvest-queue` / `REFRESH=1` |
| Triage only | `make harvest-triage` |
| Local probes | `make harvest-pipeline` |
| Manual batch | `make harvest-gemini OFFSET=0 LIMIT=10` |

Defaults: `LIMIT=2`, `ISSUES=3`, `SLEEP=6`. Free tier: use `LIMIT=2` (~20 req/day).

Scripts:

```bash
uv run python scripts/harvest/run_harvest_promotion.py --limit 2 --issues 3
uv run python scripts/harvest/run_harvest_promotion.py --create-issues
uv run python scripts/harvest/run_harvest_promotion.py --skip-harvest --skip-local --issues 3
uv run python scripts/harvest/run_harvest_promotion.py --force   # ignore content cache
```

## Pipeline steps

1. **Queue** — `.j2py/harvest/queue.txt` from `corpus-reports/*.json` (Tier A, max 50).
   Tier A: `parse_ok`, `coverage == 1.0`, `syntax_ok == false`, `unhandled_count == 0`.
2. **Local harvest** — `tests/fixtures/llm/*.java`.
3. **Gemini batch** — `state.harvest_offset` + `LIMIT`; skips cached `java_sha256` unless `--force`.
4. **Prune + triage** — dedupe `records.jsonl`, print aggregate.
5. **Issue promotion** — pattern families via `promote_harvest_signals.py`; skips
   `state.filed_signals` and open issues matching `harvest: <signal>`.

**429 quota:** batch runner exits **code 3** with resume hint. Continue with next `OFFSET`.

## After issues are filed

1. Coverage gaps → add `FUTURE_TARGETS` + [add-translation-rule](../add-translation-rule/SKILL.md)
2. Mypy-repair patterns → rule/registry work + optional harvest JSON fixture
3. Never implement filename-specific fixes

Templates:

- [signal_patterns.py](../../../scripts/harvest/signal_patterns.py)
- [.github/ISSUE_TEMPLATE/rule-layer-pattern.md](../../../.github/ISSUE_TEMPLATE/rule-layer-pattern.md)

## Local state (gitignored)

| File | Purpose |
|------|---------|
| `records.jsonl` | Harvest records |
| `usage.jsonl` | Token usage / est. cost |
| `queue.txt` | Tier-A paths |
| `state.json` | `harvest_offset`, `filed_signals` |

## If queue build fails

No reports → run corpus scan ([corpus-gap-triage](../corpus-gap-triage/SKILL.md)).

Triage existing records only:

```bash
make harvest-promote-dry
```

## Verify

```bash
uv run pytest tests/harvest/ -q
make harvest-promote-dry ISSUES=2
cat .j2py/harvest/state.json
```

## Related docs

- [docs/LLM_HARVEST.md](../../../docs/LLM_HARVEST.md)
- [docs/TRANSLATION_TARGETS.md](../../../docs/TRANSLATION_TARGETS.md)
- [docs/decisions/0017-llm-harvest-for-rule-layer-backlog.md](../../../docs/decisions/0017-llm-harvest-for-rule-layer-backlog.md)
