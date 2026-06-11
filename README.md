# j2py

j2py converts Java source to reviewable Python with line-level structural
correspondence. The goal is not a fully idiomatic rewrite; the goal is Python that a
reviewer can compare against the original Java side by side.

## Current Status

j2py is a rule-development and measurement harness for Java-to-Python translation. It is
not yet a production Spring porting tool.

Current deterministic rule support includes:

- tree-sitter Java parsing and symbol extraction
- class, nested class, interface, enum, and record skeletons
- interface abstract methods, default methods, and static methods
- fields, constructors, methods, overload stubs, and simple overload merges
- common expressions: literals, identifiers, field access, arrays, class literals,
  assignments, updates, ternaries, null checks, common collection calls, and string concat
- common stream pipelines: `map`, `filter`, `distinct`, `sorted`, simple collectors
  such as `toList`, `toSet`, `joining`, basic `groupingBy`/`toMap`, and supported
  block lambdas
- control flow: `if`/`else`, enhanced and classic `for`, `while`, `do while`,
  safe `switch` forms, `try`/`catch`/`finally`, `throw`, `break`, and `continue`
- configured import emission, naming policy, type maps, exception maps, and comment flags
- dependency-ordered directory translation
- structured diagnostics, confidence, optional validation, and optional Anthropic
  completion for partial translations

Known gaps include:

- some advanced stream collectors, long/complex chains, and certain method-reference
  contexts (many common cases like toSet/joining, distinct/sorted, basic groupingBy
  now supported via comprehensions or small helpers; block lambdas in streams handled)
- switch fall-through and complex switch rule blocks
- complex constructor dispatch and non-trivial overload bodies
- enum constructors and annotation semantics
- behavioral equivalence testing between Java and Python
- framework semantics such as Spring dependency injection or Hibernate mappings

## Quick Start

```bash
uv sync --locked
make check
```

Translate a fixture without LLM completion:

```bash
uv run j2py translate tests/fixtures/java/HelloWorld.java --no-llm --no-validate --dry-run
```

Translate a directory in dependency order:

```bash
uv run j2py translate path/to/java/root --output translated_py --no-llm
```

Use LLM completion only when `ANTHROPIC_API_KEY` is set:

```bash
ANTHROPIC_API_KEY=... uv run j2py translate SomeClass.java
```

## Quality Gates

```bash
make check         # ruff + mypy strict + normal pytest suite (excludes live_llm)
make test-targets  # roadmap xfail targets
make corpus-spring # pinned Spring Framework corpus comparison

# On-demand only (requires ANTHROPIC_API_KEY):
make test-llm-e2e  # exploratory live-LLM test of current skeleton quality
# or: ANTHROPIC_API_KEY=... uv run pytest -m live_llm tests/llm/test_e2e_llm.py -v -s
```

The current pinned Spring sample baseline is:

- parse success: 100.00%
- generated Python syntax success: 91.00%
- average skeleton coverage: 89.59% across 92 coverage-bearing files
- full-coverage files: 43 of 92 coverage-bearing files
- files with unhandled constructs: 49 of 100
- files below 80% coverage: 12 of 92 coverage-bearing files
- sample size: 100 files with committed per-file failure metrics

See [docs/CORPUS_SCOREBOARD.md](docs/CORPUS_SCOREBOARD.md) and
[docs/TRANSLATION_TARGETS.md](docs/TRANSLATION_TARGETS.md) for the implementation
workflow.

## Adding Translation Support

1. Add or update a target fixture if the construct is not yet supported.
2. Implement the smallest deterministic rule in `j2py/translate/`.
3. Graduate the behavior into normal tests once it passes.
4. Run `make check`, `make test-targets`, and `make corpus-spring`.
5. Update the Spring baseline only when the comparison has no regressions.

Material translation policy changes should get an ADR under `docs/decisions/`.
