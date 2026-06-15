# LLM harvest — backlog for the rule layer

The **LLM harvest** records what the LLM fixed when the deterministic rule layer
left gaps. It turns live translation runs into an auditable, local backlog for future
rule-layer work — without a second LLM call and without committing raw API output.

Design decision: [ADR 0017](decisions/0017-llm-harvest-for-rule-layer-backlog.md).

## Why it exists

The rule layer reports **node coverage** via `TranslationDiagnostics`. Corpus
scoreboards rank **unhandled constructs** when `coverage < 1.0`.

Live LLM runs expose a second gap class:

- **coverage == 1.0** but skeleton output **fails mypy** (undefined JDK types, broken
  overloads, missing `TypeVar`s)
- The LLM repairs these, but the repair pattern was previously lost in terminal output

Harvest captures **trigger** (why LLM ran), **repair signals** (what changed), and a
**diff excerpt** (skeleton vs final) for each file.

## What gets recorded

Recording is **automatic** whenever `translate_file(..., use_llm=True)` invokes the
LLM:

- `j2py translate SomeClass.java`
- `make test-llm-e2e`
- `make harvest-run`

Records append to a **gitignored** local log:

```text
.j2py/harvest/records.jsonl    # one JSON object per line
```

Override path: `J2PY_LLM_HARVEST_PATH=/path/to/records.jsonl`

Disable recording: `J2PY_LLM_HARVEST=0`

### Record schema (version 1)

| Field | Meaning |
|---|---|
| `schema_version` | `"1"` |
| `recorded_at` | UTC ISO timestamp |
| `source_path` | Java source file |
| `java_sha256` | Content hash (detect stale replays) |
| `model`, `prompt_version` | Repro context |
| `trigger` | Why LLM ran — see below |
| `repair_signals` | Heuristic tags from skeleton→final diff |
| `final_todos` | Remaining `TODO(j2py)` / `__j2py_todo__` in LLM output |
| `diff_excerpt` | Truncated unified diff for review |
| `status` | `open` (default) or `resolved` after rule-layer fix |

### Trigger kinds

| Kind | When |
|---|---|
| `coverage_gap` | Rule-layer `coverage < 1.0` (unhandled constructs) |
| `mypy_repair` | Full coverage but pre-LLM mypy failed |
| `syntax_repair` | Pre-LLM syntax check failed |
| `structural_repair` | Reserved for pre-LLM structural failures |

`trigger.unhandled` lists rule-layer diagnostics. `trigger.pre_validation_errors`
lists mypy/syntax messages from the skeleton.

### Repair signals (heuristic tags)

Assigned by deterministic checks in `j2py/llm/harvest.py` (unit-tested):

| Signal | Typical meaning |
|---|---|
| `protocol-stub` | New `Protocol[...]` for JDK types |
| `generic-typevar` | New `TypeVar(...)` |
| `overload-dispatch` | `@typing.overload` + dispatcher |
| `overload-runtime-to-typing` | Replaced `@overloaded` with `@typing.overload` |
| `todo-placeholder-removed` | Removed `__j2py_todo__` |
| `unsupported-stmt-removed` | Removed `# TODO(j2py): unsupported` |
| `adapter-class-introduced` | Helper class for Java interface static factories |
| `runtime-not-implemented-stub` | `NotImplementedError` left in output |
| `anonymous-class-retained` | Anonymous class pattern preserved |
| `jdk-import-removed` | Fixed bogus Java-package imports |

Tags are **approximate** — always read the diff before implementing a rule.

## Quick start

### Prerequisites

- `GEMINI_API_KEY` for `make harvest-run`, `make harvest-gemini`, and
  `make test-llm-gemini-e2e`
- `ANTHROPIC_API_KEY` for `make test-llm-e2e` (Anthropic probes)
- See [README](../README.md) live LLM section for key setup

### One-shot pipeline

```bash
make harvest-pipeline
```

Runs, in order:

1. `harvest-run` — LLM-translate probe files
2. `harvest-triage` — ranked report
3. `harvest-suggest-targets` — draft `FUTURE_TARGETS` snippets
4. `harvest-prune` — compact the jsonl

### Individual commands

```bash
make harvest-run              # translate tests/fixtures/llm/*.java with LLM (Gemini)
make harvest-gemini           # batch harvest from corpus queue (see below)
make harvest-triage           # print triage report (alias: harvest-llm)
make harvest-suggest-targets  # suggest FUTURE_TARGETS for coverage-gap rows
make harvest-prune            # dedupe jsonl
make test-llm-e2e             # full live pytest probes (also records)
```

Presets for small probe runs (`scripts/harvest/harvest_presets.py`):

```bash
uv run python scripts/harvest/run_llm_harvest.py --preset local
uv run python scripts/harvest/run_llm_harvest.py --preset constructs
```

| Preset | Files |
|---|---|
| `local` | `tests/fixtures/llm/*.java` (cheap, no corpus checkout) |
| `constructs` | local + selected `tests/fixtures/corpus/constructs/` mypy probes |

### Continuous batch harvest (Gemini)

For surfacing real gaps from large corpora (e.g. Spring), build a **queue file** from a
deterministic corpus scan, then run Gemini in batches. Requires `GEMINI_API_KEY`.

**1. Scan the corpus** (once per preset; see [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md)):

```bash
make corpus-clone-all   # if external checkouts are not present yet
uv run python scripts/corpus/translate_corpus.py \
  --preset spring-dense --limit 2000 --max-loc 0 --min-constructs 0 \
  --json-out corpus-reports/spring-scan.json
```

**2. Build the queue** — keep files with real gaps; drop `package-info.java` descriptors:

```bash
mkdir -p .j2py/harvest
jq -r '.files[] | select(
  (.path | test("package-info\\.java$") | not) and
  (.unhandled_count > 0 or .syntax_ok == false or .parse_ok == false)
) | .path' corpus-reports/spring-scan.json > .j2py/harvest/queue.txt
```

**3. Run batches** — default `LIMIT=10`, `SLEEP=6` (~10 RPM). On the free tier
(~20 requests/day for Flash), use `LIMIT=2`:

```bash
make harvest-gemini OFFSET=0 LIMIT=10
make harvest-gemini OFFSET=10 LIMIT=10   # resume next slice
make harvest-triage
```

Makefile variables: `FILE_LIST` (default `.j2py/harvest/queue.txt`), `OFFSET`, `LIMIT`,
`SLEEP`. Each Java file may trigger 1–3 LLM calls (initial + mypy repair retries).

On **429 quota**, the runner exits with code 3 and prints a resume hint. Monitor rate
limits at [ai.dev/rate-limit](https://ai.dev/rate-limit); token spend is logged to
`.j2py/harvest/usage.jsonl` (see below).

Direct script (same flags as `make harvest-gemini`):

```bash
uv run python scripts/harvest/run_llm_harvest.py \
  --llm-provider gemini \
  --file-list .j2py/harvest/queue.txt \
  --offset 0 --limit 10 \
  --sleep-seconds 6 \
  --skip-temp-paths --skip-package-info
```

## Triage report

```bash
make harvest-triage
```

Prints:

- **Trigger kinds** — why LLM ran across unique sources
- **Repair signals** — ranked rule-layer candidates
- **Pre-LLM validation buckets** — undefined-name, overload-redef, etc.
- **Example files** per repair signal

Triage **dedupes on read** (latest record per `source_path`).

Direct script:

```bash
uv run python scripts/harvest/aggregate_llm_harvest.py
uv run python scripts/harvest/aggregate_llm_harvest.py --path .j2py/harvest/records.jsonl
```

## Promoting harvest → rule-layer work

Harvest feeds three lanes depending on gap type:

| Gap type | Harvest signal | Promotion target |
|---|---|---|
| Coverage gap (`TODO`, `__j2py_todo__`) | `coverage_gap`, `unsupported-stmt-removed` | [`FUTURE_TARGETS`](TRANSLATION_TARGETS.md) |
| Mypy repair only | `protocol-stub`, `overload-dispatch`, … | Harvest JSON fixture or new mypy contract |
| Runtime stub left | `runtime-not-implemented-stub` | JDK-stub policy / ADR |

### Coverage gaps → FUTURE_TARGETS

```bash
make harvest-suggest-targets
# or save draft:
uv run python scripts/harvest/suggest_future_targets.py --write
# → scripts/harvest/drafts/future_targets_snippet.py
```

Review the snippet, then merge into `tests/targets/test_translation_targets.py`.
Skips tracking ids already registered. See [TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md).

### Mypy-repair → promoted fixture (manual)

For cases like `InterfaceDefaults` or `ObjectNameManager` (skeleton coverage already
1.0):

```bash
grep InterfaceDefaults .j2py/harvest/records.jsonl | python -m json.tool \
  > tests/fixtures/llm/harvest/interface-defaults.json
```

Reference the JSON in the PR that implements the deterministic rule.

## Live LLM tests

Exploratory pytest probes (excluded from `make check`):

```bash
make test-llm-e2e
```

Fixtures: `tests/fixtures/llm/`, `tests/llm/test_e2e_llm.py`. These also append
harvest records when they call `translate_file(..., use_llm=True)`.

---

# LLM harvest maintenance

The harvest log is **append-only** and **local**. It grows when you re-run the same
files. Maintenance is lightweight — no separate retention service.

## When to prune

| Situation | Action |
|---|---|
| After `make harvest-pipeline` or repeated `test-llm-e2e` | `make harvest-prune` (included in pipeline) |
| Triage counts look inflated | `make harvest-prune` |
| After graduating a rule | Mark record `status: "resolved"`, then prune |
| Starting fresh | `rm .j2py/harvest/records.jsonl` |

## How pruning works

Three mechanisms:

1. **Dedupe on read** — `harvest-triage` and `harvest-suggest-targets` use the latest
   row per `source_path`.
2. **Skip identical re-appends** — same file + same `java_sha256` + same
   `repair_signals` is not written again.
3. **`make harvest-prune`** — rewrites jsonl to one row per source; drops
   `status=resolved`.

```bash
make harvest-prune
uv run python scripts/harvest/prune_llm_harvest.py --dry-run   # preview counts
uv run python scripts/harvest/prune_llm_harvest.py --keep-resolved
```

Example output:

```text
kept 21 of 33 records at .j2py/harvest/records.jsonl
removed 12 duplicate or resolved rows
```

## Marking records resolved

After a rule lands and `FUTURE_TARGETS` / fixture tests pass, edit the jsonl line
(or use `jq`) to set:

```json
"status": "resolved"
```

Then `make harvest-prune` removes it.

## Inspecting records

```bash
# Pretty-print one record
grep MultiDimArray .j2py/harvest/records.jsonl | python -m json.tool

# Count lines vs unique sources
wc -l .j2py/harvest/records.jsonl
uv run python -c "
import json; from pathlib import Path
lines = Path('.j2py/harvest/records.jsonl').read_text().splitlines()
paths = {json.loads(l)['source_path'] for l in lines if l.strip()}
print(len(lines), 'lines,', len(paths), 'unique sources')
"
```

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `J2PY_LLM_HARVEST` | `1` | Set to `0` to disable recording |
| `J2PY_LLM_HARVEST_PATH` | `.j2py/harvest/records.jsonl` | Alternate log path |
| `J2PY_LLM_USAGE` | `1` | Set to `0` to disable token usage logging |
| `J2PY_LLM_USAGE_PATH` | `.j2py/harvest/usage.jsonl` | Alternate usage log path |
| `ANTHROPIC_API_KEY` | — | Required for `harvest-run` / `test-llm-e2e` |
| `GEMINI_API_KEY` | — | Required for `make harvest-gemini` |

## Token usage logging (Gemini)

Each Gemini API call records **`usage_metadata`** token counts to a separate append-only
log (also gitignored):

```text
.j2py/harvest/usage.jsonl
```

Each line includes `provider`, `model`, `kind` (`api_call` or `cache_hit`),
`source_path` (when known), token counts, and an **estimated USD cost** from published
Flash pricing (approximate — check [Google AI pricing](https://ai.google.dev/pricing)).

The batch harvest runner prints per-file and session summaries:

```text
  LLM  Foo.java confidence=0.85 usage: api_calls=2, cache_hits=0, tokens in=1200, out=800, total=2000, est=$0.0012
usage: api_calls=10, cache_hits=1, tokens in=6000, out=4000, total=10000, est=$0.0060
Usage log: .j2py/harvest/usage.jsonl
```

Disable with `J2PY_LLM_USAGE=0`. Override path with `J2PY_LLM_USAGE_PATH`.

Implementation: `j2py/llm/usage.py` (client hook + harvest runner summary).

## Implementation map

| Component | Path |
|---|---|
| Record builder + heuristics | `j2py/llm/harvest.py` |
| Token usage logging | `j2py/llm/usage.py` |
| Pipeline hook | `j2py/pipeline.py` (`record_llm_repair`) |
| Batch runner | `scripts/harvest/run_llm_harvest.py` |
| Triage report | `scripts/harvest/aggregate_llm_harvest.py` |
| FUTURE_TARGETS drafts | `scripts/harvest/suggest_future_targets.py` |
| Prune / compact | `scripts/harvest/prune_llm_harvest.py` |
| Probe presets | `scripts/harvest/harvest_presets.py` |
| Unit tests | `tests/llm/test_harvest.py`, `tests/harvest/` |

## Related docs

- [TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) — graduated vs future xfail workflow
- [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md) — deterministic rule-layer scoreboards
- [ADR 0017](decisions/0017-llm-harvest-for-rule-layer-backlog.md) — design decision
- [ADR 0003](decisions/0003-layered-translation-pipeline.md) — rule → LLM layering
