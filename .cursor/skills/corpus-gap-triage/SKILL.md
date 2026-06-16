---
name: corpus-gap-triage
description: >-
  Triage j2py rule-layer gaps using corpus presets, committed baselines, and hotspot
  ranking. Use when finding what to fix next, running make corpus-hotspots, comparing
  dense baselines, interpreting coverage vs syntax failures, or feeding harvest queue
  builds. Corpus harness never calls the LLM.
---

# Corpus gap triage

Measures **deterministic rule-layer** progress only. No LLM, no `use_llm=True`.

Read first: [docs/CORPUS_SCOREBOARD.md](../../../docs/CORPUS_SCOREBOARD.md).

## Decision tree

```text
make corpus-hotspots
    │
    ├─ unhandled_count > 0  ──► add-translation-rule OR defer FUTURE_TARGETS
    ├─ coverage < 1.0       ──► add-translation-rule (parse_ok may still be true)
    ├─ parse_ok == false    ──► parser gap (rare) — not harvest Tier A
    ├─ coverage==1.0, syntax_ok==false ──► harvest-promote (Tier A queue)
    └─ baseline regression on -check ──► fix branch; do NOT refresh baseline to hide
```

## When to use

- “What should we fix next?” / hotspot ranking / scoreboard
- Before/after a rule-layer PR (regression check)
- Before `make harvest-queue` (need `corpus-reports/*.json` scans)

## Prerequisites

```bash
make corpus-clone-all                    # once on main checkout
export J2PY_CORPUS_ROOT=/path/to/main    # worktrees — reuse .corpus/
```

Clones: `$J2PY_CORPUS_ROOT/.corpus/` (gitignored). Scan JSON: `corpus-reports/` (gitignored).

## Quick triage (no clones)

```bash
make corpus-hotspots
```

Read the sections:

| Section | Action |
|---------|--------|
| **SCORECARD** | Cross-library coverage / syntax / unhandled summary |
| **SYNTAX FAILURES** | Often Tier A harvest candidates (`cov=1.00`, invalid Python) |
| **PARSE FAILURES** | Parser bugs — fix `parse/`, not harvest |
| **UNHANDLED HOTSPOTS** | Rule-layer TODO clusters — pattern-family rules |

## Per-preset check (needs clones)

Committed baselines: `guava-dense`, `commons-lang-dense`, `jackson-dense`,
`caffeine-dense`, `spring-dense`. Exploratory only: `spring-broad` (no baseline).

```bash
make corpus-list-presets
make corpus-guava-dense-check
make corpus-commons-lang-dense-check
make corpus-jackson-dense-check
make corpus-caffeine-dense-check
make corpus-spring-dense-check          # includes construct mini-corpus
```

Run without baseline diff:

```bash
make corpus-<name>-dense
uv run python scripts/corpus/translate_corpus.py --preset guava-dense --help
```

### Pick a preset

| Your change touches | Run |
|---------------------|-----|
| Collections / Guava patterns | `corpus-guava-dense-check` |
| Utility Java | `corpus-commons-lang-dense-check` |
| Annotations / beans | `corpus-jackson-dense-check` |
| Lambdas / concurrent caches | `corpus-caffeine-dense-check` |
| Framework + construct mix | `corpus-spring-dense-check` |

## Gap classes → next step

| Signal | Meaning | Next step |
|--------|---------|-----------|
| `unhandled_count > 0` | `# TODO(j2py)` / unhandled AST | [add-translation-rule](../add-translation-rule/SKILL.md) |
| `coverage < 1.0` | Incomplete rule layer | Same, or defer via `FUTURE_TARGETS` |
| `parse_ok == false` | Java parse failure | Parser — not LLM harvest |
| `coverage == 1.0`, `syntax_ok == false` | Valid skeleton, bad Python/mypy | [harvest-promote](../harvest-promote/SKILL.md) |
| `-check` regression | Branch worse than baseline | Fix or revert |
| Hotspot across libraries | Cross-cutting pattern | Pattern-family GitHub issue |

**Tier A queue** (for harvest) requires: `parse_ok`, `coverage == 1.0`, `syntax_ok == false`,
`unhandled_count == 0`, not `package-info.java`. See `scripts/harvest/build_harvest_queue.py`.

## Exploratory scan → harvest queue

```bash
uv run python scripts/corpus/translate_corpus.py \
  --preset spring-dense --limit 2000 --max-loc 0 --min-constructs 0 \
  --json-out corpus-reports/spring-scan.json
make harvest-queue REFRESH=1
```

Queue capped at 50 paths; prefers smaller files. See [docs/LLM_HARVEST.md](../../../docs/LLM_HARVEST.md).

## Baseline update (intentional only)

```bash
make corpus-<name>-dense-check           # review diff — must be improvement
make corpus-<name>-dense-update-baseline
git add tests/fixtures/corpus/*-baseline.json
```

CI runs the full dense matrix on merge.

## Construct mini-corpus

`tests/fixtures/corpus/constructs/` — graduated constructs run in `make check` via
`tests/targets/`. See
[tests/fixtures/corpus/constructs/README.md](../../../tests/fixtures/corpus/constructs/README.md).

## Anti-patterns

- One `.corpus/` file = one bug fix (fix the **pattern**)
- Refresh baseline to greenwash regressions
- Re-clone in every worktree
- LLM inside corpus harness

## Verify

```bash
make corpus-hotspots
make corpus-<relevant>-dense-check   # when clones available
make check
```

## Related docs

- [docs/TRANSLATION_TARGETS.md](../../../docs/TRANSLATION_TARGETS.md)
- [docs/LLM_HARVEST.md](../../../docs/LLM_HARVEST.md)
- [scripts/corpus/corpus_presets.py](../../../scripts/corpus/corpus_presets.py)
