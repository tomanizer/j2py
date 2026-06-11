# Spring Corpus Scoreboard

The Spring corpus harness measures deterministic rule-layer progress against real Spring
Framework Java source. It never calls the LLM layer.

The default scoreboard is pinned to:

- Spring remote: `https://github.com/spring-projects/spring-framework.git`
- Spring ref: `0c60266986197a191ff33eb498ebc8bac3dc933f`
- Sample size: `100`
- Modules:
  - `spring-core/src/main/java`
  - `spring-beans/src/main/java`

The committed baseline lives at:

```text
tests/fixtures/corpus/spring-sample-baseline.json
```

Current committed baseline:

- parse success rate: 100.00%
- generated Python syntax success rate: 91.00%
- files included in coverage metrics: 92 of 100
- average skeleton coverage: 89.56%
- full-coverage files: 43 of 92 coverage-bearing files
- files with unhandled constructs: 49 of 100
- files below 80% coverage: 12 of 92 coverage-bearing files
- per-file metrics committed for parse failures, syntax failures, coverage,
  unhandled node types, and unhandled reasons

Run the scoreboard against an existing checkout:

```bash
make corpus-spring
```

Run a quick local 25-file smoke sample without comparing the committed baseline:

```bash
make corpus-spring-smoke
```

Clone or refresh the pinned Spring checkout explicitly:

```bash
uv run python scripts/corpus/translate_spring_sample.py --clone --compare-baseline
```

Regenerate the committed baseline intentionally:

```bash
make corpus-spring-update-baseline
```

Generated detailed reports are written under `corpus-reports/`, which is ignored by git.
The default `make check` gate does not clone Spring or run the corpus harness; this keeps
CI fast and deterministic.

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

Use the comparison output to decide whether a translation rule improved or regressed the
real corpus before updating the baseline.

Coverage aggregates only include files where the translator recorded at least one
handled or unhandled construct. Files with no measured constructs, such as
`package-info.java`, still count in parse/syntax rates and per-file reports but do not
pull the average coverage or below-threshold count toward zero.
