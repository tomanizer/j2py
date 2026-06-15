# ADR 0017 — LLM harvest for rule-layer backlog

**Date:** 2026-06-15
**Status:** Accepted

## Context

The rule layer (`translate/skeleton.py` and friends) reports **node coverage** via
`TranslationDiagnostics`, and corpus scoreboards rank **unhandled constructs**. That
works well when coverage `< 1.0`.

Live LLM runs show a second gap class: **coverage == 1.0 but output fails mypy or
structural checks**. The LLM repairs these cases — Protocol stubs for JDK types,
`@typing.overload` dispatch, `TypeVar` for generic interfaces, adapter classes for
Java interface static factories — but those repairs are lost unless someone copies
terminal output by hand.

We need a **simple, transparent** trail from “LLM fixed X” → “rule layer should learn
X”, without a second LLM call, without hiding data in caches, and without polluting
committed Python output.

## Decision

When the pipeline invokes the LLM, **append one JSON Lines record** per file to a
local harvest log:

```
.j2py/harvest/records.jsonl   # gitignored; one object per line
```

Each record is **deterministic**: built from data the pipeline already has (skeleton,
final output, pre-LLM validation, rule diagnostics) plus lightweight diff heuristics.
No model-generated metadata.

### Record schema (version 1)

| Field | Purpose |
|---|---|
| `schema_version` | `"1"` |
| `recorded_at` | UTC ISO timestamp |
| `source_path` | Java file path |
| `java_sha256` | Content hash — detect stale replays |
| `model`, `prompt_version` | Repro context |
| `trigger` | Why LLM ran: `coverage_gap`, `mypy_repair`, `syntax_repair`, `structural_repair`, or combinations |
| `trigger.unhandled` | Rule-layer unhandled diagnostics |
| `trigger.pre_validation_errors` | Pre-LLM mypy/syntax messages from the skeleton |
| `trigger.structural_errors` | Pre-LLM structural verification failures (reserved; not populated in v1) |
| `repair_signals` | Heuristic tags inferred from skeleton→final diff (e.g. `protocol-stub`, `overload-dispatch`) |
| `final_todos` | Remaining `TODO(j2py)` / `__j2py_todo__` in LLM output — explicit backlog |
| `diff_excerpt` | Truncated unified diff for human review |
| `status` | `open` until a human marks promoted or resolved |

### Repair signal heuristics (transparent rules)

Tags are assigned by fixed string/AST checks on skeleton vs final output, for example:

- `overload-dispatch` — `@typing.overload` appears in final, not skeleton
- `protocol-stub` — new `Protocol[...]` classes
- `generic-typevar` — new `TypeVar(...)`
- `todo-placeholder-removed` — `__j2py_todo__` removed
- `unsupported-stmt-removed` — `# TODO(j2py): unsupported` removed
- `runtime-not-implemented-stub` — `NotImplementedError` left in final output

Heuristics live in `j2py/llm/harvest.py` and are unit-tested.

### Workflow

1. **Record** — automatic on every `translate_file(..., use_llm=True)` (`J2PY_LLM_HARVEST=1`, default on).
2. **Batch collect** — `make harvest-run` (or `--preset constructs` for mypy probes).
3. **Aggregate** — `make harvest-triage` ranks clusters by `repair_signals` and trigger kinds / validation buckets.
4. **Draft targets** — `make harvest-suggest-targets` prints `FUTURE_TARGETS` snippets for
   coverage-gap records; `--write` saves to `scripts/harvest/drafts/`.
5. **One-shot** — `make harvest-pipeline` runs steps 2–4 and **prune**.
6. **Promote** — copy a record or draft into `tests/fixtures/llm/harvest/<name>.json` or
   merge the snippet into `tests/targets/test_translation_targets.py`.
7. **Resolve** — set record ``status`` to ``resolved`` in the jsonl after the rule lands,
   then run ``make harvest-prune`` to drop it; or delete the file entirely.

Full operator guide: [LLM_HARVEST.md](../LLM_HARVEST.md).

**Pruning:** the log is append-only and gitignored. Re-translating the same file creates
duplicate rows. Triage dedupes on read; ``make harvest-prune`` rewrites the file to the
latest row per ``source_path`` and drops ``status=resolved`` rows. Identical back-to-back
appends are skipped at write time. See [LLM_HARVEST.md](../LLM_HARVEST.md#maintenance).

Disable recording: ``J2PY_LLM_HARVEST=0``.

### Non-goals

- No automatic GitHub issue creation.
- No LLM-generated “explanation” field (avoids hallucinated rationale).
- No committed jsonl by default — only promoted fixtures are reviewed in git.

## Consequences

**Positive**

- Every live or production LLM run leaves an auditable backlog artifact.
- Rule-layer work can cite concrete before/after diffs and tags.
- Aligns with existing corpus hotspot triage without conflating coverage with mypy gaps.

**Negative**

- Local jsonl grows unbounded; users may need occasional cleanup.
- Heuristic tags are approximate — triage still requires human judgment.
- Promoted fixtures must be redacted if they ever contained sensitive source (unlikely
  for open corpus).

## References

- [ADR 0003](0003-layered-translation-pipeline.md) — layered rule → LLM pipeline
- [ADR 0010](0010-post-llm-structural-verification.md) — structural verification inputs
- [LLM_HARVEST.md](../LLM_HARVEST.md) — operator guide and maintenance
- `j2py/llm/harvest.py` — implementation
- `scripts/harvest/aggregate_llm_harvest.py` — triage report
