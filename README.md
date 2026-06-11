# j2py

j2py converts Java source to reviewable Python with line-level structural
correspondence. The goal is not a fully idiomatic rewrite; the goal is Python that a
reviewer can compare against the original Java side by side.

## Current Status

j2py is a rule-development and measurement harness for Java-to-Python translation. It is
not yet a production Spring porting tool.

Current deterministic rule support includes:

- tree-sitter Java parsing and symbol extraction
- class, nested class, basic local/anonymous class helpers, interface,
  basic and constructor-backed enum, and record skeletons
- interface abstract methods, default methods, and static methods
- fields, constructors, methods, and overloads: chained constructor delegation and
  builder-style forwarding merge into default parameters; type-dispatch overload
  groups emit same-named defs behind a vendored `@overloaded` runtime dispatcher
  (ADR 0009)
- common expressions: literals, identifiers, field access, arrays, class literals,
  assignments, updates, ternaries, null checks, common collection calls, and string concat
- common stream pipelines: `map`, `filter`, `distinct`, `sorted`, simple collectors
  such as `toList`, `toSet`, `joining`, basic `groupingBy`/`toMap`, and supported
  block lambdas
- control flow: `if`/`else`, enhanced and classic `for`, `while`, `do while`,
  safe `switch` forms, `try`/`catch`/`finally`, `throw`, `break`, and `continue`
- configured import emission, naming policy, type maps, exception maps, and comment flags
- dependency-ordered directory translation
- structured diagnostics, confidence, default validation, post-LLM structural
  verification, and optional Anthropic completion for partial translations
- side-by-side Java/Python review through the `j2py compare` CLI command

Known gaps include:

- one corpus construct still tracked as a strict xfail target: advanced stream collectors
  and long chains (`AdvancedStreams`)
- overload groups whose erased Python signatures collide (e.g. `int` vs `long`)
  and static-method overload groups still fall back to manual-dispatch TODOs
- enum constant class bodies, complex enum static initialization, and annotation semantics
- behavioral equivalence testing between Java and Python
- framework semantics such as Spring dependency injection or Hibernate mappings

Graduated in `make check` (no longer listed as gaps): common switch forms, interface
defaults/statics, text blocks, sealed classes, records, instance `synchronized(this)`,
local `var` inference, switch fall-through, anonymous class instance fields, and
`super.method(...)` receiver calls.

## Quick Start

Install the alpha from PyPI:

```bash
pip install --pre j2py-converter
j2py --help
```

The PyPI distribution is `j2py-converter`; the import package and console command remain
`j2py`.

For local development:

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

Open a side-by-side Java/Python diff in VS Code, generating the Python file first if
needed:

```bash
uv run j2py compare tests/fixtures/java/HelloWorld.java --no-llm
```

Print the compare paths without opening an editor:

```bash
uv run j2py compare tests/fixtures/java/HelloWorld.java --no-open --no-llm
```

Use LLM completion only when `ANTHROPIC_API_KEY` is set:

```bash
ANTHROPIC_API_KEY=... uv run j2py translate SomeClass.java
```

## Quality Gates

```bash
make check         # ruff + mypy strict + normal pytest suite (excludes behavior, live_llm)
make test-behavior # Java/Python stdout/stderr/exit-code equivalence tests (requires a JDK)
make test-targets  # future xfail roadmap targets only (graduated targets run in make check)
make release-check # alpha release gate: check + targets + behavior + distribution check
make corpus-spring-dense-check # preferred Spring + curated-construct corpus comparison
make corpus-spring # historical lexical Spring-only corpus comparison

# Corpus modes:
make corpus-spring-dense  # preferred density-based Spring + curated-construct sample
make corpus-spring-broad  # extra modules + curated constructs/ mini-corpus

# On-demand only (requires ANTHROPIC_API_KEY):
make test-llm-e2e  # exploratory live-LLM test of current skeleton quality
# or: ANTHROPIC_API_KEY=... uv run pytest -m live_llm tests/llm/test_e2e_llm.py -v -s
```

The preferred dense corpus baseline includes Spring files plus curated non-Spring
construct fixtures and is stored at `tests/fixtures/corpus/spring-dense-baseline.json`.

The historical lexical Spring-only baseline is:

- parse success: 100.00%
- generated Python syntax success: 93.00%
- average skeleton coverage: 94.71% across 92 coverage-bearing files
- full-coverage files: 65 of 92 coverage-bearing files
- files with unhandled constructs: 27 of 100
- files below 80% coverage: 4 of 92 coverage-bearing files
- sample size: 100 files with committed per-file failure metrics

See [docs/CORPUS_SCOREBOARD.md](docs/CORPUS_SCOREBOARD.md) and
[docs/TRANSLATION_TARGETS.md](docs/TRANSLATION_TARGETS.md) for the implementation
workflow.

## Adding Translation Support

1. Add or update a target fixture if the construct is not yet supported.
2. Implement the smallest deterministic rule in `j2py/translate/`.
3. Graduate the behavior into normal tests once it passes.
4. Run `make check`, `make test-targets`, and `make corpus-spring-dense-check`.
5. Update the dense corpus baseline only when the comparison has no regressions.

Material translation policy changes should get an ADR under `docs/decisions/`.

## Alpha Release Notes

`j2py-converter` is published as an alpha package. Expect incomplete Java construct
coverage, diagnostics for unsupported regions, and non-production behavior on large
framework-heavy codebases. The existing `j2py` PyPI name is owned by an unrelated
Jupyter notebook converter, so this project uses the distinct distribution name
`j2py-converter`.

See [docs/RELEASING.md](docs/RELEASING.md) for the alpha release checklist.

## License

MIT. See [LICENSE](LICENSE).
