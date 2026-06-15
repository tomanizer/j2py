# Corpus scoreboard

j2py is a general Java-to-Python library. **Corpus presets** are pinned checkouts of
popular open-source Java libraries used to stress-test the deterministic rule layer. They
never call the LLM layer and do not define product scope or target runtime.

The harness measures rule-layer progress against several libraries plus a small curated
construct mini-corpus. Presets live in `scripts/corpus/corpus_presets.py`; committed
baselines live under `tests/fixtures/corpus/`.

## Multi-library presets

| Preset | Library | Modules (summary) | Baseline | Construct mix |
|--------|---------|-------------------|----------|---------------|
| `guava-dense` | Google Guava | `collect`, `base` | `guava-dense-baseline.json` | — |
| `commons-lang-dense` | Apache Commons Lang | `src/main/java` | `commons-lang-dense-baseline.json` | — |
| `jackson-dense` | Jackson databind | `src/main/java` | `jackson-dense-baseline.json` | — |
| `caffeine-dense` | Caffeine | `caffeine/src/main/java` | `caffeine-dense-baseline.json` | — |
| `spring-dense` | Spring Framework | `spring-core`, `spring-beans` | `spring-dense-baseline.json` | yes (`--include-constructs`) |
| `spring-broad` | Spring Framework | `spring-context` | `spring-broad-baseline.json` | yes |
| `spring-lexical` | Spring Framework | `spring-core`, `spring-beans` | `spring-sample-baseline.json` | — (historical lexical sample) |

Dense presets (except `spring-lexical`) use `--strategy density --max-loc 250
--min-constructs 5` unless noted in the preset definition.

| Preset | What it stress-tests |
|--------|----------------------|
| `guava-dense` | Generics-heavy collections and utilities |
| `commons-lang-dense` | Classic utility Java without framework magic |
| `jackson-dense` | Annotation and bean-introspection patterns |
| `caffeine-dense` | Concurrent cache code and lambdas |
| `spring-dense` | Framework-style core/beans Java plus construct fixtures |
| `spring-broad` | Broader `spring-context` surface plus construct fixtures |
| `spring-lexical` | Historical lexical Spring sample for continuity with older reports |

## Curated construct mini-corpus

A curated "constructs" mini-corpus lives in `tests/fixtures/corpus/constructs/`. These
are tiny, focused Java files that guarantee coverage of important language features used
across large codebases (interface defaults + statics, text blocks, anonymous and inner
classes, switch fall-through, advanced enums, enum constant class bodies, sealed types,
records, and more).

Density presets with `--include-constructs` (notably `spring-dense` and `spring-broad`)
mix these fixtures into the sampled run. All graduated construct files also run in
`make check` via `tests/targets/`. See
[docs/TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) and
[tests/fixtures/corpus/constructs/README.md](../tests/fixtures/corpus/constructs/README.md).

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

## Per-preset commands

For any preset `<name>` (e.g. `guava-dense`, `spring-dense`):

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
make corpus-spring-dense-check      # Spring dense + construct fixtures
make corpus-spring-broad            # broader spring-context sample + constructs
```

Historical Spring-only lexical baseline (continuity with older reports):

```bash
make corpus-spring                  # compare lexical sample vs spring-sample-baseline.json
make corpus-spring-smoke            # quick 25-file smoke, no baseline compare
make corpus-spring-update-baseline  # regenerate lexical baseline intentionally
```

Low-level entry point (any preset):

```bash
uv run python scripts/corpus/translate_spring_sample.py --preset guava-dense --clone
uv run python scripts/corpus/translate_spring_sample.py --preset spring-dense --compare-baseline
```

Generated detailed reports are written under `corpus-reports/` (ignored by git).

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
handled or unhandled construct. Files with no measured constructs, such as
`package-info.java`, still count in parse/syntax rates and per-file reports but do not
pull the average coverage or below-threshold count toward zero.

## Contributor workflow

For translation-rule PRs:

1. Run `make check` (required — no corpus clone needed).
2. After `make corpus-clone-all`, run at least:
   - `make corpus-spring-dense-check` when constructs or broad rule-layer behavior may
     shift, and
   - one additional library preset relevant to the change (e.g.
     `make corpus-guava-dense-check` for generics/collections,
     `make corpus-commons-lang-dense-check` for utility-class patterns).
3. Use `make corpus-hotspots` when triaging gaps across libraries.
4. Update a baseline with `make corpus-<preset>-update-baseline` only after confirming no
   regressions in comparison mode.

## CI and `make check`

The default `make check` gate does not clone external libraries or run the corpus
harness; this keeps CI fast and deterministic. A separate GitHub Actions workflow
(`.github/workflows/corpus.yml`) runs the pinned `spring-dense` baseline comparison when
translation or corpus files change.

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

## Reference: `spring-dense` snapshot

The `spring-dense` preset remains a high-signal scoreboard because it mixes real
framework Java with the construct mini-corpus. It is pinned to:

- remote: `https://github.com/spring-projects/spring-framework.git`
- ref: `0c60266986197a191ff33eb498ebc8bac3dc933f`
- sample size: `100`
- modules: `spring-core/src/main/java`, `spring-beans/src/main/java`
- selection: density + `--include-constructs`

Committed baseline metrics (as of last baseline refresh):

- parse success rate: 100.00%
- generated Python syntax success rate: 98.00%
- files included in coverage metrics: 43 of 100
- average skeleton coverage: 100.00%
- full-coverage files: 43 of 43 coverage-bearing files
- files with unhandled constructs: 0 of 100
- files below 80% coverage: 0 of 43 coverage-bearing files
- all curated construct fixtures are included in the selected sample
