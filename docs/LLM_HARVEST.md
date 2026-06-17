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

- `GEMINI_API_KEY` for batch harvest and promotion (`make harvest-run`, `make harvest-gemini`,
  `make harvest-promote`, `make test-llm-gemini-e2e`)
- The Gemini SDK extra for packaged installs: `pip install "j2py-converter[gemini]"`.
  Contributor installs using the repository `dev` extra include it for local harvest and
  live Gemini probes.
- `ANTHROPIC_API_KEY` for `make test-llm-e2e` (Anthropic probes)
- Optional: `gh` CLI authenticated for `make harvest-promote-issues`
- See [README](../README.md) live LLM section for key setup

Makefile targets load `.env` from the checkout, then `$J2PY_CORPUS_ROOT/.env` (for git
worktrees), then the login shell (`LOAD_GEMINI_ENV` in the Makefile).

### Recommended workflows

| Goal | Command |
|------|---------|
| Triage existing records + draft pattern issues (no LLM) | `make harvest-promote-dry ISSUES=3` |
| Full promotion slice (queue → harvest → triage → drafts) | `make harvest-promote LIMIT=2 ISSUES=3` |
| Same + create GitHub issues | `make harvest-promote-issues` |
| Local probe harvest + FUTURE_TARGETS drafts | `make harvest-pipeline` |
| Rebuild Tier-A corpus queue | `make harvest-queue REFRESH=1` |
| Manual batch harvest only | `make harvest-gemini OFFSET=0 LIMIT=10` |
| Triage report only | `make harvest-triage` |

Variables: `LIMIT` (Gemini files per promote run, default `2`), `ISSUES` (pattern issues
per run, default `3`), `OFFSET` / `SLEEP` / `FILE_LIST` for `harvest-gemini`.

### Makefile reference

| Target | What it does |
|--------|----------------|
| `harvest-promote` | Queue refresh → local probes → Gemini batch → prune → triage → draft issues |
| `harvest-promote-issues` | Same + `gh issue create` for each draft |
| `harvest-promote-dry` | Prune → triage → draft issues only (`--skip-harvest --skip-local`) |
| `harvest-queue` | Build `.j2py/harvest/queue.txt` from `corpus-reports/*.json` (Tier A) |
| `harvest-queue REFRESH=1` | Force queue rebuild |
| `harvest-run` | LLM-translate `tests/fixtures/llm/*.java` (Gemini) |
| `harvest-gemini` | Batch harvest from queue file |
| `harvest-triage` | Ranked triage report (alias: `harvest-llm`) |
| `harvest-suggest-targets` | Draft `FUTURE_TARGETS` snippets for coverage-gap rows |
| `harvest-prune` | Dedupe jsonl (latest row per source; drop resolved) |
| `harvest-pipeline` | `harvest-run` → triage → suggest-targets → prune |
| `test-llm-e2e` | Anthropic live pytest probes (also records) |
| `test-llm-gemini-e2e` | Gemini live probe |

Agent skill for promotion: [`.cursor/skills/harvest-promote/SKILL.md`](../.cursor/skills/harvest-promote/SKILL.md).

### Local state files (gitignored)

All under `.j2py/harvest/` unless overridden:

| File | Purpose |
|------|---------|
| `records.jsonl` | One harvest record per LLM translation (`J2PY_LLM_HARVEST_PATH`) |
| `usage.jsonl` | Gemini token usage and estimated cost (`J2PY_LLM_USAGE_PATH`) |
| `queue.txt` | Tier-A corpus paths for batch harvest |
| `state.json` | Promotion progress: `harvest_offset`, `filed_signals`, timestamps |

### Git worktrees

Harvest state and API keys normally live on the **main** checkout. In a worktree:

```bash
export J2PY_CORPUS_ROOT=/path/to/main/j2py
make harvest-promote-dry ISSUES=2
```

This reuses `$J2PY_CORPUS_ROOT/.env`, `.j2py/harvest/`, and corpus checkouts under
`.corpus/`.

### One-shot local probe pipeline

```bash
make harvest-pipeline
```

Runs: `harvest-run` → `harvest-triage` → `harvest-suggest-targets` → `harvest-prune`.
Use this for cheap construct probes, not corpus-scale promotion (use `harvest-promote`).

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

**2. Build the queue** — Tier A: `coverage == 1.0`, `syntax_ok == false`,
`unhandled_count == 0` (mypy/syntax gaps the LLM can repair):

```bash
make harvest-queue              # build if missing or corpus reports are newer
make harvest-queue REFRESH=1    # force rebuild
# or: uv run python scripts/harvest/build_harvest_queue.py --force
```

Manual filter (any gap class):

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
make harvest-promote LIMIT=2             # orchestrated slice + triage + issue drafts
make harvest-triage
```

Makefile variables: `FILE_LIST` (default `.j2py/harvest/queue.txt`), `OFFSET`, `LIMIT`,
`SLEEP`. Each Java file may trigger 1–3 LLM calls (initial + mypy repair retries).

**Content cache:** paths already in `records.jsonl` at the same `java_sha256` are skipped
(`cache Foo.java (unchanged harvest record)`). Re-run with `--force` or
`--no-skip-cached` on the promotion or batch scripts.

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

### Promoting harvest → GitHub issues (pattern families)

Triage lists **example files per repair signal**. A signal is almost always a **pattern
family** (AST node, diagnostic reason, registry gap) — not a bug in one Java file.

**Do not** file issues anchored on a single example (`Fix AssertProbe.java`). Agents will
implement point fixes: one xfail passes, one LLM diff is copied, the general diagnostic
remains.

File issues anchored on the **pattern**, with examples as evidence only.

#### Workflow

1. **Prune and triage**

   ```bash
   make harvest-prune && make harvest-triage
   ```

2. **Group by signal + diagnostic**, not by first example file

   Pick a repair signal (e.g. `unsupported-stmt-removed`, `protocol-stub`,
   `jdk-import-removed`). Collect every clean source path for that signal — exclude pytest
   temp dirs (`/pytest-`, `/var/folders/`).

   ```bash
   uv run python -c "
   import json
   from collections import defaultdict
   from pathlib import Path
   from j2py.llm.harvest import latest_harvest_records, load_harvest_records

   records = latest_harvest_records(load_harvest_records(Path('.j2py/harvest/records.jsonl')))
   by_sig = defaultdict(set)
   for r in records:
       p = str(r.get('source_path', ''))
       if '/pytest-' in p or '/var/folders/' in p:
           continue
       for s in r.get('repair_signals') or []:
           by_sig[s].add(p)
   for sig in sorted(by_sig, key=lambda s: -len(by_sig[s])):
       print(f'{len(by_sig[sig]):3} {sig}')
       for path in sorted(by_sig[sig])[:8]:
           print(f'     {path}')
   "
   ```

3. **Choose roles for sources**

   | Role | Purpose |
   |------|---------|
   | Minimal fixture | Smallest file to develop the rule (often under `tests/fixtures/llm/`) |
   | Regression peers | Other harvest hits that must improve with the same rule |
   | Corpus evidence | Large `.corpus/` files — cite in issue; extract minimal repro into `tests/fixtures/` when implementing |

4. **Open issue using the template**

   - GitHub UI: **New issue → Rule layer pattern (from harvest)**
   - Template file: [`.github/ISSUE_TEMPLATE/rule-layer-pattern.md`](../.github/ISSUE_TEMPLATE/rule-layer-pattern.md)
   - Draft copy: [`.github/issue-drafts/harvest-pattern-issue-template.md`](../.github/issue-drafts/harvest-pattern-issue-template.md)

   ```bash
   gh issue create --title "Rule layer: … (harvest: …)" \
     --label "enhancement,rule-layer" \
     --body-file .github/issue-drafts/harvest-pattern-issue-template.md
   ```

5. **Wire tracking**

   - Coverage gaps: add/update `FUTURE_TARGETS` with `tracking="issue-NNN"` (minimal fixture only — acceptance still pattern-level)
   - Mypy repair: optional harvest JSON under `tests/fixtures/llm/harvest/`
   - Link related issues when patterns overlap (e.g. `#298` import registry vs `#296` Comparator types)

#### Issue body checklist

Every harvest-promoted issue should include:

| Section | Content |
|---------|---------|
| **Pattern family** | AST node, diagnostic, harvest signal — explicit “not a single-file fix” |
| **Mechanism** | Translator module / registry; general mapping rule |
| **Evidence table** | All clean harvest sources; mark minimal fixture vs peer |
| **Pattern-level acceptance** | Parametrised tests, multiple files, signal drop on re-harvest |
| **Anti-patterns** | Ban filename checks, one-diff copy-paste, single-xfail fixes |
| **Verify** | `make check`, `make test-targets`, targeted pytest, re-harvest |

#### Promotion lanes (unchanged)

| Gap type | Harvest signal | GitHub issue focus | Repo artifact |
|---|---|---|---|
| Coverage gap | `coverage_gap`, `unsupported-stmt-removed`, `todo-placeholder-removed` | Statement/expression **visitor rule** | `FUTURE_TARGETS` + fixtures |
| Mypy repair | `protocol-stub`, `generic-typevar`, `jdk-import-removed`, … | **Type registry** + emission policy | Harvest JSON + construct fixtures |
| Overload | `overload-dispatch`, `overload-runtime-to-typing` | **`overloads.py` tier** (distinguish instance vs static groups) | Overload probe fixtures |
| Adapter / factory | `adapter-class-introduced` | Interface static factory → concrete adapter | Construct fixtures |

#### Example titles (good vs bad)

| Bad (point fix) | Good (pattern family) |
|-----------------|-------------------------|
| Fix AssertProbe.java | Rule layer: Java assert statements (harvest: unsupported-stmt-removed) |
| ObjectNameManager mypy | Rule layer: static JDK overload groups + platform stubs (harvest: overload-runtime-to-typing) |
| AnonymousComparator Protocol | Rule layer: JDK Comparator + anonymous class typing (harvest: protocol-stub) |

#### Automated promotion pipeline

One command runs queue refresh → Gemini batch → prune → triage → pattern-family issue
drafts (or GitHub create). Progress is tracked in `.j2py/harvest/state.json`.

```bash
make harvest-promote              # LIMIT=2 ISSUES=3; drafts issues to stdout
make harvest-promote-issues       # same + gh issue create
make harvest-promote-dry          # no LLM — prune, triage, draft only
make harvest-queue                # rebuild Tier A queue from corpus-reports/
make harvest-queue REFRESH=1      # force queue rebuild
```

| Step | Script / target |
|------|-----------------|
| Build Tier A queue | `scripts/harvest/build_harvest_queue.py` |
| Orchestrator | `scripts/harvest/run_harvest_promotion.py` |
| Issue bodies | `scripts/harvest/promote_harvest_signals.py` + `signal_patterns.py` |
| Agent skill | `.cursor/skills/harvest-promote/SKILL.md` |

Queue is rebuilt when missing or when any `corpus-reports/*.json` is newer than
`queue.txt`. Gemini batch advances `state.harvest_offset` until the queue is exhausted
(then `--refresh-queue` after new corpus scans).

**Duplicate-issue guards:** pattern families already in `state.filed_signals` are skipped.
Before filing, the promoter also checks for open GitHub issues matching
`harvest: <signal>` via `gh issue list`. Use `make harvest-promote-dry` to preview drafts
without creating issues.

**Content cache:** paths already in `records.jsonl` at the same `java_sha256` are skipped
automatically. Queue offset syncs past cached entries on each promote run. Re-run with
`--force` or `--no-skip-cached`.

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
3. **Content cache (batch runs)** — `run_llm_harvest.py` and `run_harvest_promotion.py`
   skip files whose `java_sha256` already appears in `records.jsonl` unless `--force` or
   `--no-skip-cached`.
4. **`make harvest-prune`** — rewrites jsonl to one row per source; drops
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
| `J2PY_CORPUS_ROOT` | — | Main checkout path for worktrees (`.env`, `.j2py/harvest/`, `.corpus/`) |
| `ANTHROPIC_API_KEY` | — | Required for `test-llm-e2e` |
| `GEMINI_API_KEY` | — | Required for `harvest-run`, `harvest-gemini`, `harvest-promote` |

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
| Worktree `.env` fallback | `j2py/dotenv.py` |
| Batch runner | `scripts/harvest/run_llm_harvest.py` |
| Promotion orchestrator | `scripts/harvest/run_harvest_promotion.py` |
| Pattern-family issue drafts | `scripts/harvest/promote_harvest_signals.py` |
| Signal → pattern metadata | `scripts/harvest/signal_patterns.py` |
| Tier-A queue builder | `scripts/harvest/build_harvest_queue.py` |
| Content cache | `scripts/harvest/harvest_cache.py` |
| Promotion state | `scripts/harvest/harvest_state.py` |
| Triage helpers | `scripts/harvest/triage_lib.py` |
| Triage report | `scripts/harvest/aggregate_llm_harvest.py` |
| FUTURE_TARGETS drafts | `scripts/harvest/suggest_future_targets.py` |
| Prune / compact | `scripts/harvest/prune_llm_harvest.py` |
| Probe presets | `scripts/harvest/harvest_presets.py` |
| Agent skill | `.cursor/skills/harvest-promote/SKILL.md` |
| GitHub issue template | `.github/ISSUE_TEMPLATE/rule-layer-pattern.md` |
| Unit tests | `tests/llm/test_harvest.py`, `tests/harvest/` |

## Related docs

- [TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) — graduated vs future xfail workflow
- [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md) — deterministic rule-layer scoreboards
- [ADR 0017](decisions/0017-llm-harvest-for-rule-layer-backlog.md) — design decision
- [ADR 0003](decisions/0003-layered-translation-pipeline.md) — rule → LLM layering
