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
- fields, constructors, methods, overload stubs, and simple overload merges
- common expressions: literals, identifiers, field access, arrays, class literals,
  assignments, updates, ternaries, null checks, common collection calls, and string concat
- control flow: `if`/`else`, enhanced and classic `for`, `while`, `do while`,
  `try`/`catch`/`finally`, `throw`, `break`, and `continue`
- configured import emission, naming policy, type maps, exception maps, and comment flags
- dependency-ordered directory translation
- structured diagnostics, confidence, optional validation, and optional Anthropic
  completion for partial translations

Known gaps include:

- lambdas, streams, and method references
- `switch` and switch expressions
- complex constructor dispatch and non-trivial overload bodies
- enum constructors/default interface methods/annotation semantics
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
make check         # ruff + mypy strict + normal pytest suite
make test-targets  # roadmap xfail targets
make corpus-spring # pinned Spring Framework corpus comparison
```

The current pinned Spring sample baseline is:

- parse success: 100.00%
- generated Python syntax success: 100.00%
- average skeleton coverage: 84.33%
- full-coverage files: 8 of 25
- files with unhandled constructs: 16 of 25

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
