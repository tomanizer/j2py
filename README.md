# j2py

**j2py** is a Java-to-Python source translator. It converts Java classes to Python that
preserves line-level structural correspondence — same method order, same control flow,
camelCase -> snake_case naming — so reviewers can audit output against the original Java
side by side. The goal is reviewable equivalence, not a fully idiomatic rewrite.
After deterministic conversion a file can be passed to an LLM for an additional conversion attempt.

## How it works

```
Java source
  → parse (tree-sitter-java)
  → analyze (symbols, dependency graph)
  → translate (deterministic rule layer, then optional LLM completion)
  → validate (syntax, lint, types)
  → Python output
```

The **rule layer** handles common language constructs deterministically (~70% of typical
code). Where rules stop, an optional configured LLM provider fills gaps using disk-cached
prompts.
Every file gets a **confidence** score based on rule-layer coverage and structured
diagnostics for anything left unhandled.

## Status

**Alpha.** The library is usable for experimentation, fixture-driven development, and
batch translation of real Java projects, but construct coverage is still incomplete and
output on large enterprise codebases will contain TODOs and review warnings.

Deterministic support today includes:

- tree-sitter Java parsing and symbol extraction
- class, nested class, local/anonymous class helpers, interface, enum, and record skeletons
- interface abstract methods, default methods, and static methods
- fields, constructors, methods, and overloads: chained constructor delegation,
  builder-style forwarding merged into default parameters, and type-dispatch overload
  groups via a vendored `@overloaded` runtime dispatcher (ADR 0009)
- common expressions: literals, identifiers, field access, arrays, class literals,
  assignments, updates, ternaries, null checks, collection calls, string concat, and
  typed `get(...)` lowering for lists, maps, and common API receivers
- stream pipelines: `map`, `filter`, `flatMap`, `distinct`, `sorted`, collectors such as
  `toList`, `toSet`, `joining`, `groupingBy`/`mapping`, `toMap`, and block lambdas
- control flow: `if`/`else`, enhanced and classic `for`, `while`, `do while`, safe
  `switch` forms, `try`/`catch`/`finally`, `throw`, `break`, and `continue`
- configured import emission, naming policy, type maps, exception maps, and comment flags
- dependency-ordered directory translation
- structured diagnostics, confidence scoring, validation, post-LLM structural
  verification, and optional Anthropic or Gemini completion
- side-by-side Java/Python review via `j2py compare`

Known gaps include:

- overload groups whose erased Python signatures collide (e.g. `int` vs `long`) and
  other ambiguous overload groups that still fall back to manual-dispatch TODOs
- complex enum static initialization beyond translated enum constant class bodies
- annotation semantics beyond syntactic metadata shells
- runtime/framework behavior (dependency injection, persistence mappings, container
  lifecycle) — j2py translates source structure, not application frameworks

## Quick start

Install the alpha from PyPI:

```bash
pip install --pre j2py-converter
j2py --help
```

The PyPI distribution is **`j2py-converter`**; the import package and CLI command are
**`j2py`**. (The bare `j2py` name on PyPI is owned by an unrelated project.)

Local development:

```bash
uv sync --locked
make check
```

Translate a file without LLM completion:

```bash
uv run j2py translate tests/fixtures/java/HelloWorld.java --no-llm --no-validate --dry-run
```

Translate a directory in dependency order:

```bash
uv run j2py translate path/to/java/root --output translated_py --no-llm
```

Skip unchanged files on repeated directory runs:

```bash
uv run j2py translate path/to/java/root --output translated_py --incremental
```

Generate review reports:

```bash
uv run j2py translate path/to/java/root --output translated_py --dashboard dashboard.html
uv run j2py translate SomeClass.java --report review.html
```

Watch a source tree and incrementally re-translate changed Java files:

```bash
uv run j2py watch path/to/java/root --output translated_py --no-llm
```

Side-by-side review in VS Code:

```bash
uv run j2py compare tests/fixtures/java/HelloWorld.java --no-llm
```

Print compare paths without opening an editor:

```bash
uv run j2py compare tests/fixtures/java/HelloWorld.java --no-open --no-llm
```

LLM completion with the default Anthropic provider (requires `ANTHROPIC_API_KEY`):

```bash
ANTHROPIC_API_KEY=... uv run j2py translate SomeClass.java
```

LLM completion with Gemini Flash (requires `GEMINI_API_KEY`):

```bash
GEMINI_API_KEY=... uv run j2py translate SomeClass.java \
  --llm-provider gemini --model gemini-3.5-flash
```

Configuration can live in `j2py.yaml`, `j2py.toml`, `[tool.j2py]` in
`pyproject.toml`, or `j2py_config.py`. See
[docs/configuration.md](docs/configuration.md) for the schema.

## Quality gates

```bash
make check         # ruff + mypy strict + pytest (excludes behavior, live_llm)
make test-behavior # Java/Python stdout/stderr/exit-code equivalence (requires JDK)
make test-targets  # future xfail roadmap targets (empty while all targets graduated)
make release-check # alpha release gate: release-test + dist-check (3.11+ in CI publish workflow)
```

### Benchmark corpus

Translation quality is measured against a **multi-library corpus**: pinned checkouts of
Spring Framework, Guava, Apache Commons Lang, Jackson, and Caffeine, plus small curated
construct fixtures under `tests/fixtures/corpus/`. These libraries are open-source stress
tests for the deterministic rule layer — not product scope or target runtime.

```bash
make corpus-list-presets              # show all pinned presets
make corpus-clone-all                 # one-time: clone all checkouts into .corpus/
make corpus-guava-dense-check         # Guava collect/base vs baseline
make corpus-commons-lang-dense-check  # Commons Lang utilities vs baseline
make corpus-jackson-dense-check       # Jackson databind vs baseline
make corpus-caffeine-dense-check      # Caffeine cache code vs baseline
make corpus-spring-dense-check        # Spring dense preset + construct fixtures
make corpus-hotspots                  # rank gaps across all committed baselines
```

Presets and baselines live in `scripts/corpus/corpus_presets.py` and
`tests/fixtures/corpus/`. In git worktrees, set `J2PY_CORPUS_ROOT` to your main checkout
so scripts reuse `$J2PY_CORPUS_ROOT/.corpus/`. Regenerate a baseline with
`make corpus-<name>-update-baseline` only after comparison shows no regressions.

See [docs/CORPUS_SCOREBOARD.md](docs/CORPUS_SCOREBOARD.md),
[docs/TRANSLATION_TARGETS.md](docs/TRANSLATION_TARGETS.md), and the full
[documentation index](docs/README.md).

On-demand live LLM evaluation (excluded from `make check`):

```bash
make test-llm-e2e
# or: ANTHROPIC_API_KEY=... uv run pytest -m live_llm tests/llm/test_e2e_llm.py -v -s
```

## Adding translation rules

1. Add or update a Java/Python fixture pair under `tests/fixtures/`.
2. Implement the smallest deterministic rule in `j2py/translate/`.
3. Graduate the behavior into normal tests once it passes.
4. Run `make check` and relevant corpus checks, such as `make corpus-guava-dense-check`
   for generics/collections or `make corpus-spring-dense-check` when construct-mix
   behavior may shift.
5. Update a corpus baseline only when comparison shows no regressions.

Material translation policy changes should get an ADR under `docs/decisions/`.

## Alpha release notes

`j2py-converter` is published as an alpha package. Expect incomplete construct
coverage, diagnostics for unsupported regions, and manual review on production-scale
codebases. See [docs/RELEASING.md](docs/RELEASING.md) for the release checklist.

## License

MIT. See [LICENSE](LICENSE).
