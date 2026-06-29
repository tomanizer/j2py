# 0.8.1 performance baseline

This page records the 0.8.1 release performance baseline for representative local
translation and reporting paths. The numbers remain the 0.7.0 representative baseline
until a dedicated performance probe is rerun for 0.8.1; no code optimization was merged
as part of this release-prep slice.

## Environment

- Date: 2026-06-29 release-prep audit
- Baseline source: 0.7.0 release performance probe
- OS: macOS Darwin 22.6.0 x86_64
- Python: 3.11.14 from the checked-in `.venv`
- LLM calls: disabled

## Commands

The benchmark probe used the public pipeline APIs for stage timings and the checked-in
CLI commands for Spring wiring and corpus reporting:

```bash
.venv/bin/python scripts/corpus/translate_corpus.py \
  --repo tests/fixtures/corpus \
  --module constructs \
  --limit 5 \
  --json-out /private/tmp/j2py-issue-585-perf/constructs-5.json \
  --csv-out /private/tmp/j2py-issue-585-perf/constructs-5.csv

make corpus-hotspots
```

The Spring fixture path translated:

- `tests/fixtures/java/SpringWiringController.java`
- `tests/fixtures/java/SpringJdbcConfiguration.java`
- `tests/fixtures/java/JdbcTemplateSqlAlchemyScaffold.java`

with:

```bash
.venv/bin/j2py translate <fixture.java> \
  --config tests/fixtures/framework/spring_wiring_plugin_config.py \
  --output /private/tmp/j2py-issue-585-perf/spring-cli/<fixture>.py \
  --no-llm \
  --no-validate
.venv/bin/j2py-wire generate /private/tmp/j2py-issue-585-perf/spring-cli \
  --target fastapi \
  --output /private/tmp/j2py-issue-585-perf/spring-cli/wiring
.venv/bin/j2py-wire validate /private/tmp/j2py-issue-585-perf/spring-cli \
  --target fastapi \
  --wiring-dir /private/tmp/j2py-issue-585-perf/spring-cli/wiring \
  --format json
```

`j2py-wire validate` returned exit code 1 for warnings-only missing project runtime
providers, which is the expected boundary for this fixture path.

## Results

| Scenario | Fixture or path | Rounds | Median | Min | Max |
|---|---|---:|---:|---:|---:|
| Small parse only | `tests/fixtures/java/HelloWorld.java` | 15 | 0.0004s | 0.0004s | 0.0007s |
| Small parse + symbol extraction | `tests/fixtures/java/HelloWorld.java` | 15 | 0.0008s | 0.0007s | 0.0108s |
| Small parse + symbols + rule translation | `tests/fixtures/java/HelloWorld.java` | 15 | 0.0058s | 0.0049s | 0.0450s |
| Small validation of translated output | `tests/fixtures/java/HelloWorld.java` | 5 | 0.3508s | 0.3424s | 0.4349s |
| Small full pipeline, no LLM, with validation | `tests/fixtures/java/HelloWorld.java` | 5 | 0.3418s | 0.3197s | 0.3688s |
| Medium package graph setup | `tests/fixtures/case_study/commons_lang_tuple/java` | 7 | 0.0123s | 0.0119s | 0.0143s |
| Medium package translate, no validation | `tests/fixtures/case_study/commons_lang_tuple/java` | 5 | 0.1760s | 0.1517s | 0.2071s |
| Medium package validation pass only | `tests/fixtures/case_study/commons_lang_tuple/java` | 5 | 0.4680s | 0.4087s | 0.5915s |
| Medium package translate with validation | `tests/fixtures/case_study/commons_lang_tuple/java` | 5 | 0.4776s | 0.3897s | 0.4916s |
| Spring fixture CLI translate + wire + validate | Spring/JDBC fixture trio above | 3 | 3.4194s | 3.1706s | 3.7095s |
| Corpus reporting slice | local `tests/fixtures/corpus/constructs`, limit 5 | 3 | 0.4831s | 0.4707s | 0.5444s |

The local corpus slice reported:

- files scanned: 5
- parse success: 100%
- generated Python syntax success: 100%
- average skeleton coverage: 100%
- files with unhandled constructs: 0

`make corpus-hotspots` completed successfully and read committed baseline JSON only. Its
scorecard still identifies static-import resolution and deterministic overload dispatch
as large quality backlog clusters; those are translation-quality priorities rather than
performance regressions.

## Stage analysis

- Parse, symbol extraction, dependency graph construction, and rule translation are not
  the bottleneck for these fixtures.
- Validation dominates small and medium local runs because of validation subprocess
  startup: `validate_source` and `validate_directory` invoke ruff and mypy subprocesses.
  Directory translation already batches validation through `validate_directory`, so the
  medium package does not pay a separate ruff/mypy startup per file.
- The Spring CLI path is slower mostly because the measured smoke invokes multiple CLI
  processes plus `j2py-wire`. This is acceptable for smoke validation. For larger
  projects, prefer directory translation and batched validation instead of repeatedly
  translating one file per process.
- Corpus reporting on committed fixtures is sub-second for a five-file slice. External
  dense corpus checks are expected to scale with checkout size, file count, and optional
  baseline comparison.

## Optimization decision

No code optimization was merged in this slice. The only obvious hot area is validation
subprocess startup, but the release path already uses batched directory validation where
it matters. More aggressive changes, such as persistent checker daemons, checker result
caches, or a syntax-only validation mode, would change validation semantics or
operational complexity and should be handled through a dedicated design issue if the
release profile shows real user pain.

## Remaining limits

- Single-file validated translations have a fixed ruff/mypy startup cost of roughly
  0.3-0.4s on this machine.
- Multi-file workflows should use directory translation so validation stays batched.
- Spring smoke timings include process startup and project-boundary warnings from
  `j2py-wire validate`; they are not pure translator timings.
- These numbers are local wall-clock measurements, not statistically rigorous benchmarks
  across platforms.
