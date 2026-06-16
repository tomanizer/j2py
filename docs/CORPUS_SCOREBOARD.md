# Corpus scoreboard

j2py is a general Java-to-Python library. **Corpus presets** are pinned checkouts of
popular open-source Java libraries used to stress-test the deterministic rule layer. They
never call the LLM layer and do not define product scope or target runtime.

The harness measures rule-layer progress against several libraries plus a small curated
construct mini-corpus. Presets live in `scripts/corpus/corpus_presets.py`; committed
baselines live under `tests/fixtures/corpus/`.

## Multi-library presets

| Preset | Library | Modules (summary) | Committed baseline | Construct mix |
|--------|---------|-------------------|--------------------|---------------|
| `guava-dense` | Google Guava | `collect`, `base` | `guava-dense-baseline.json` | — |
| `commons-lang-dense` | Apache Commons Lang | `src/main/java` | `commons-lang-dense-baseline.json` | — |
| `jackson-dense` | Jackson databind | `src/main/java` | `jackson-dense-baseline.json` | — |
| `caffeine-dense` | Caffeine | `caffeine/src/main/java` | `caffeine-dense-baseline.json` | — |
| `spring-dense` | Spring Framework | `spring-core`, `spring-beans`, DI annotation/config packages, stereotypes | `spring-dense-baseline.json` | yes (`--include-constructs`) |
| `spring-app-dense` | Spring Framework | context-indexer samples, framework-docs web/data, webmvc tests, scannable examples | `spring-app-dense-baseline.json` | yes (`--include-constructs`) |
| `spring-lexical` | Spring Framework | `spring-core`, `spring-beans` | `spring-sample-baseline.json` | — (historical lexical sample) |
| `spring-broad` | Spring Framework | `spring-context` | — (exploratory; no committed baseline) | yes |

Density presets (except `spring-lexical`) use `--strategy density --max-loc 1000
--min-loc 20 --min-constructs 5` unless noted in the preset definition.

| Preset | What it stress-tests |
|--------|----------------------|
| `guava-dense` | Generics-heavy collections and utilities |
| `commons-lang-dense` | Classic utility Java without framework magic |
| `jackson-dense` | Annotation and bean-introspection patterns |
| `caffeine-dense` | Concurrent cache code and lambdas |
| `spring-dense` | Framework core/beans Java, Spring DI annotations/stereotypes, construct fixtures |
| `spring-app-dense` | Application-layer Spring: `@RestController`, `@Service`/`@Repository`, `@Transactional`, JPA `@Entity` samples from framework test fixtures and docs |
| `spring-lexical` | Historical lexical Spring sample for continuity with older reports |
| `spring-broad` | Broader `spring-context` surface plus construct fixtures (local exploration) |

## Committed baseline scorecard

Run the live dashboard from committed JSON (no corpus clones required):

```bash
make corpus-hotspots
```

As of the current committed baselines, `make corpus-hotspots` reports approximately:

| Preset | Avg coverage | Syntax OK | Unhandled files | Full-coverage files |
|--------|-------------|-----------|-----------------|-------------------|
| `spring-dense` | 100% | 100% | 0/100 | 43/43 |
| `commons-lang-dense` | ~100% | 100% | 1/100 | 99/100 |
| `jackson-dense` | ~99.5% | 99% | 6/100 | 83/89 |
| `caffeine-dense` | ~99.6% | 97% | 8/36 | 25/33 |
| `guava-dense` | ~98% | 94% | 14/100 | 86/100 |
| `spring-lexical` | ~100% | 100% | 7/100 | 92/99 |

Re-run `make corpus-hotspots` after refreshing any baseline. The command also prints
syntax/parse failures and a ranked hotspot backlog for cross-library triage (#152).

## Curated construct mini-corpus

A curated "constructs" mini-corpus lives in `tests/fixtures/corpus/constructs/`. These
are tiny, focused Java files that guarantee coverage of important language features used
across large codebases (interface defaults + statics, text blocks, anonymous and inner
classes, switch fall-through, advanced enums, enum constant class bodies, sealed types,
records, and more).

Density presets with `--include-constructs` (`spring-dense`, `spring-app-dense`, and
exploratory `spring-broad`) mix these fixtures into the sampled run. All graduated construct files
also run in `make check` via `tests/targets/`. See
[docs/TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) and
[tests/fixtures/corpus/constructs/README.md](../tests/fixtures/corpus/constructs/README.md).
Because this directory is part of committed corpus baselines, deferred strict-xfail
targets and corpus-derived fast regressions that should not change baselines belong under
`tests/fixtures/java/targets/` instead.

## Setup

External git checkouts are **not** in the j2py repository. They live under
`.corpus/<checkout-dir>/` (gitignored).

```bash
make corpus-list-presets   # show pinned presets
make corpus-clone-all      # one-time: clone all preset checkouts
```

In a **git worktree**, point at the main checkout's clones instead of re-downloading:

```bash
export J2PY_CORPUS_ROOT=/path/to/j2py   # directory that contains .corpus/
make corpus-commons-lang-dense-check
```

CI uses the same clone layout inside the GitHub Actions workspace. Each dense baseline
matrix job runs with `--clone`, so it creates or refreshes only the checkout needed for
that preset under the job-local `.corpus/` directory. Local worktrees should continue to
set `J2PY_CORPUS_ROOT` to avoid duplicating those external clones.

## Per-preset commands

For presets with a **committed baseline** (`guava-dense`, `commons-lang-dense`,
`jackson-dense`, `caffeine-dense`, `spring-dense`, `spring-app-dense`):

```bash
make corpus-<name>                  # run without baseline comparison
make corpus-<name>-check            # compare against committed baseline
make corpus-<name>-update-baseline  # intentional baseline refresh after review
```

Examples:

```bash
make corpus-guava-dense-check
make corpus-commons-lang-dense-check
make corpus-jackson-dense-check
make corpus-caffeine-dense-check
make corpus-spring-dense-check      # Spring dense preset + construct fixtures
make corpus-spring-app-dense-check  # Spring app-layer samples (REST, JPA, @Transactional)
```

Historical Spring lexical baseline (`spring-lexical` preset):

```bash
make corpus-spring                  # compare vs spring-sample-baseline.json
make corpus-spring-smoke            # quick 25-file smoke, no baseline compare
make corpus-spring-update-baseline  # regenerate lexical baseline intentionally
```

Exploratory broader Spring sample (`spring-broad`; no committed baseline or `-check`):

```bash
make corpus-spring-broad
```

Low-level entry point (any preset):

```bash
uv run python scripts/corpus/translate_corpus.py --preset guava-dense --clone
uv run python scripts/corpus/translate_corpus.py --preset spring-dense --compare-baseline
```

## Reports workflow

| When | Command | Output |
|------|---------|--------|
| Rule-layer PR, before push | `make corpus-<name>-check` for Spring dense + a relevant library | stdout diff vs baseline; fails on regression |
| Cross-library triage / backlog grooming | `make corpus-hotspots` | terminal scorecard + ranked clusters |
| Deep dive on one preset | `make corpus-<name>` | `corpus-reports/<name>.json` and `.csv` |
| Structured hotspot export | `uv run python scripts/corpus/aggregate_hotspots.py --json-out corpus-reports/hotspots.json` | JSON backlog for issue filing |
| Intentional baseline refresh | `make corpus-<name>-update-baseline` after clean `-check` | updates `tests/fixtures/corpus/<name>-baseline.json` |

`corpus-reports/` is gitignored. Attach relevant terminal output or JSON snippets to PRs
when baseline metrics move. After changing any `*-baseline.json`, run
`make corpus-hotspots` and include the updated scorecard summary in the PR body.

## Cross-corpus triage

Rank rule-layer gaps across **all** committed baselines (unhandled reason clusters plus
syntax/parse failures that coverage metrics can hide):

```bash
make corpus-hotspots
uv run python scripts/corpus/aggregate_hotspots.py --top 12
uv run python scripts/corpus/aggregate_hotspots.py --json-out corpus-reports/hotspots.json
```

See #152 for the backlog opened from the first triage pass.

## Scoreboard metrics

- parse success rate
- generated Python syntax success rate
- files included in coverage metrics
- average skeleton coverage
- full-coverage files
- files with unhandled constructs
- files below the 80% coverage threshold
- top unhandled node types
- top unhandled reasons
- per-file parse/syntax failures, coverage drops, unhandled count increases, and new
  unhandled reasons compared with the committed baseline

Newer runs can report additional signals (strategy used, max-loc / min-constructs filters,
number of curated construct files mixed in, rough "construct density").

Coverage aggregates only include files where the translator recorded at least one
handled or unhandled construct. `package-info.java` files are excluded from sampling by
default (use `--include-package-info` to opt in); they are package descriptors with no
real class body and would otherwise displace meaningful sources in dense presets.

## Contributor workflow

For translation-rule PRs:

1. Run `make check` (required — no corpus clone needed).
2. After `make corpus-clone-all`, run the most relevant local dense checks before
   pushing:
   - `make corpus-spring-dense-check` when constructs or broad rule-layer behavior may
     shift, and
   - one additional library preset relevant to the change (e.g.
     `make corpus-guava-dense-check` for generics/collections,
     `make corpus-commons-lang-dense-check` for utility-class patterns).
3. CI enforces every committed dense baseline (`spring-dense`, `spring-app-dense`,
   `guava-dense`, `commons-lang-dense`, `jackson-dense`, and `caffeine-dense`) before merge.
4. Use `make corpus-hotspots` when triaging gaps across libraries or after baseline
   updates.
5. Update a baseline with `make corpus-<name>-update-baseline` only after confirming no
   regressions in comparison mode.

## CI and `make check`

The default `make check` gate does not clone external libraries or run the corpus
harness; this keeps the required unit/type/lint gate fast and deterministic.

`.github/workflows/corpus.yml` runs when the translator, corpus harness, or dependency
files change:

1. **Dense baseline matrix** — clones the checkout for each committed dense preset and
   fails on regression for `spring-dense`, `spring-app-dense`, `guava-dense`,
   `commons-lang-dense`, `jackson-dense`, and `caffeine-dense`.
2. **`corpus-hotspots` scorecard** — reads committed `*-baseline.json` files only; no
   clones. Surfaces multi-library baseline drift and validates hotspot aggregation.

The dense matrix intentionally pays extra clone time on translation-related PRs so
regressions across committed library baselines are visible before merge. Historical
`spring-lexical` and exploratory `spring-broad` remain local/manual unless a PR
intentionally refreshes those baselines.

## Known parser exclusions

Some corpus presets omit individual files when tree-sitter-java produces ERROR nodes for
valid modern Java that j2py still translates. Exclusions are listed in
`CorpusPreset.exclude_paths` (`scripts/corpus/corpus_presets.py`) and recorded in baseline
metadata as `exclude_paths`.

Baseline comparison treats older metadata that omitted `exclude_paths` as equivalent to
`exclude_paths: []` only when the current run also has no exclusions. Non-empty exclusion
lists remain part of the comparability contract.

| Preset | Excluded path | Root cause |
|--------|---------------|------------|
| `guava-dense` | `guava/src/com/google/common/base/Platform.java` | Jspecify type-use `@Nullable` before varargs (`@Nullable Object @Nullable ... args`) — tree-sitter-java ERROR; skeleton translation reaches full coverage (#160). |

## Reference: `spring-dense` pins

The `spring-dense` preset remains a high-signal scoreboard because it mixes real
framework Java with the construct mini-corpus. It is pinned to:

- remote: `https://github.com/spring-projects/spring-framework.git`
- ref: `0c60266986197a191ff33eb498ebc8bac3dc933f`
- sample size: `200` (or fewer when a preset's module tree is smaller, e.g. Caffeine)
- modules: `spring-core/src/main/java`, `spring-beans/src/main/java`,
  `spring-beans/.../factory/annotation`, `spring-beans/.../factory/config`,
  `spring-context/.../context/annotation`, `spring-context/.../stereotype`
- pinned path prefixes (always sampled): `beans/factory/annotation`, `context/stereotype`
- selection: density + `--include-constructs`

For current metrics, use the [committed baseline scorecard](#committed-baseline-scorecard)
above rather than a static snapshot in this doc.

## Reference: `spring-app-dense` pins

The `spring-app-dense` preset stress-tests application-layer Spring patterns using
framework **test fixtures and documentation samples** (not a Spring Boot checkout). It
reuses the same `spring-framework` git ref as `spring-dense` and applies an
**annotation pre-filter**: only files containing at least one `@Name` from the preset's
`require_annotations` list are eligible for density sampling (curated constructs and
pinned path prefixes are always included).

- modules: `spring-context-indexer/.../sample`, `framework-docs`, `spring-web`,
  `spring-webmvc`, `spring-context`, `spring-tx`, `integration-tests`
- pinned path prefixes (always sampled): entire `context-indexer/.../sample/` tree
- `require_annotations`: web/DI/JPA/transactional annotation simple names (see
  `scripts/corpus/annotation_filter.py`)
- selection: annotation filter + density + `--include-constructs`

Baseline metadata records `annotation_family_file_counts` (files per annotation family)
for transparency. **Node coverage may stay high** on empty annotated stubs — use the
**enterprise readiness** block in each baseline's `summary.enterprise` (and
`make corpus-hotspots` scorecard columns `bodies`, `stubs`, `ann_warn`) alongside
family counts for gap triage; semantic annotation lowering is tracked separately
([#334](https://github.com/tomanizer/j2py/issues/334),
[#335](https://github.com/tomanizer/j2py/issues/335)).

### Enterprise readiness metrics

Each corpus run adds `summary.enterprise` (and per-file `method_body_count`,
`annotation_use_count`, `annotation_warning_count`):

| Field | Meaning |
|-------|---------|
| `method_body_file_rate` | Share of sampled files with at least one non-empty method/constructor body |
| `annotation_only_stub_rate` | Files with enterprise `@Annotation` uses but zero method bodies |
| `annotation_warning_file_rate` | Files emitting annotation-related semantic warnings |
| `total_annotation_warnings` | Count of warnings whose reason mentions "annotation" |

These complement `average_coverage` — a `@RestController` shell can score 100% node
coverage while still being an annotation-only stub with zero translated behavior.
