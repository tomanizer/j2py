# Spring Corpus Scoreboard

The Spring corpus harness measures deterministic rule-layer progress against real Spring
Framework Java source. It never calls the LLM layer.

The preferred progress scoreboard is the dense Spring + curated-construct corpus.
It combines real Spring Framework files with the focused non-Spring construct files
under `tests/fixtures/corpus/constructs/`, using density sampling to prefer small,
construct-rich examples.

The preferred baseline is pinned to:

- Spring remote: `https://github.com/spring-projects/spring-framework.git`
- Spring ref: `0c60266986197a191ff33eb498ebc8bac3dc933f`
- Sample size: `100`
- Modules:
  - `spring-core/src/main/java`
  - `spring-beans/src/main/java`
- Selection: `--strategy density --max-loc 250 --min-constructs 5 --include-constructs`

A curated "constructs" mini-corpus lives in `tests/fixtures/corpus/constructs/`. These
are tiny, focused non-Spring files that guarantee coverage of important Java features
used across Spring-style codebases (interface defaults + statics, text blocks,
anonymous/sophisticated inner classes, switch fall-through + complex rules, advanced
enums with constructors/methods, etc.). They are included in the preferred dense
baseline and directly support the followup roadmap items under the #47 parent.

The preferred committed baseline lives at:

```text
tests/fixtures/corpus/spring-dense-baseline.json
```

The historical lexical Spring-only baseline lives at:

```text
tests/fixtures/corpus/spring-sample-baseline.json
```

Current preferred dense baseline:

- parse success rate: 100.00%
- generated Python syntax success rate: 98.00%
- files included in coverage metrics: 43 of 100
- average skeleton coverage: 98.75%
- full-coverage files: 38 of 43 coverage-bearing files
- files with unhandled constructs: 5 of 100
- files below 80% coverage: 0 of 43 coverage-bearing files
- all curated non-Spring construct fixtures are included in the selected sample

Current historical lexical baseline:

- parse success rate: 100.00%
- generated Python syntax success rate: 93.00%
- files included in coverage metrics: 92 of 100
- average skeleton coverage: 94.71%
- full-coverage files: 65 of 92 coverage-bearing files
- files with unhandled constructs: 27 of 100
- files below 80% coverage: 4 of 92 coverage-bearing files
- per-file metrics committed for parse failures, syntax failures, coverage,
  unhandled node types, and unhandled reasons

Run the preferred dense scoreboard against an existing checkout:

```bash
make corpus-spring-dense
```

Compare the preferred dense scoreboard against the committed baseline:

```bash
make corpus-spring-dense-check
```

Regenerate the preferred dense baseline intentionally:

```bash
make corpus-spring-dense-update-baseline
```

Run the historical lexical Spring-only scoreboard:

```bash
make corpus-spring
```

Run a quick local 25-file smoke sample without comparing the committed baseline:

```bash
make corpus-spring-smoke
```

For broader coverage (extra modules + the curated constructs/ mini-corpus):

```bash
make corpus-spring-broad
```

Clone or refresh the pinned Spring checkout explicitly for the preferred dense corpus:

```bash
uv run python scripts/corpus/translate_spring_sample.py \
  --clone \
  --strategy density \
  --max-loc 250 \
  --min-constructs 5 \
  --include-constructs \
  --baseline tests/fixtures/corpus/spring-dense-baseline.json \
  --compare-baseline
```

Regenerate the historical lexical baseline intentionally:

```bash
make corpus-spring-update-baseline
```

Generated detailed reports are written under `corpus-reports/`, which is ignored by git.
The default `make check` gate does not clone Spring or run the corpus harness; this keeps
CI fast and deterministic. A separate GitHub Actions workflow (`.github/workflows/corpus.yml`)
runs the pinned baseline comparison when translation or corpus files change.

Scoreboard metrics:

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

Use `make corpus-spring-dense-check` to decide whether a translation rule improved or
regressed the preferred corpus before updating the dense baseline. Use the historical
lexical baseline only when continuity with older reports matters.

Coverage aggregates only include files where the translator recorded at least one
handled or unhandled construct. Files with no measured constructs, such as
`package-info.java`, still count in parse/syntax rates and per-file reports but do not
pull the average coverage or below-threshold count toward zero.
