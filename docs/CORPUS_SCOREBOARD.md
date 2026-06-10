# Spring Corpus Scoreboard

The Spring corpus harness measures deterministic rule-layer progress against real Spring
Framework Java source. It never calls the LLM layer.

The default scoreboard is pinned to:

- Spring remote: `https://github.com/spring-projects/spring-framework.git`
- Spring ref: `0c60266986197a191ff33eb498ebc8bac3dc933f`
- Sample size: `25`
- Modules:
  - `spring-core/src/main/java`
  - `spring-beans/src/main/java`

The committed baseline lives at:

```text
tests/fixtures/corpus/spring-sample-baseline.json
```

Run the scoreboard against an existing checkout:

```bash
make corpus-spring
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
- average skeleton coverage
- full-coverage files
- files with unhandled constructs
- top unhandled node types
- top unhandled reasons

Use the comparison output to decide whether a translation rule improved or regressed the
real corpus before updating the baseline.
