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
Every file gets a **confidence** score based on rule-layer coverage, validation status,
and semantic warnings, plus structured diagnostics for anything left unhandled.
An optional LLM review pass can run after translation as a non-mutating second opinion:
it records structured findings without changing generated Python, coverage, or confidence.

## Status

**Beta.** The library is usable for experimentation, fixture-driven development, and
batch translation of real Java projects. The deterministic rule layer reaches high node
coverage on pinned dense corpus samples, but behavioral equivalence at library scale is
still early, some cross-file/framework boundaries require project policy or manual fixups,
and output on large enterprise codebases will contain review warnings and known
correctness gaps.

Deterministic support today includes:

- tree-sitter Java parsing and symbol extraction
- class, nested class, local/anonymous class helpers, interface, enum, and record skeletons
- interface abstract methods, default methods, and static methods
- fields, constructors, methods, and overloads: chained constructor delegation,
  builder-style forwarding merged into default parameters, and type-dispatch overload
  groups via a vendored `@overloaded` runtime dispatcher (ADR 0009)
- common expressions: literals, identifiers, field access, arrays, class literals,
  assignments, updates, ternaries, null checks, collection calls, string concat,
  `String.charAt`, and typed `get(...)` lowering for lists, maps, indexed-predicate APIs,
  and common API receivers
- stream pipelines: `map`, `filter`, `flatMap`, `distinct`, `sorted`, collectors such as
  `toList`, `toSet`, `joining`, `groupingBy`/`mapping`, `toMap`, and block lambdas
- control flow: `if`/`else`, enhanced and classic `for`, `while`, `do while`, safe
  `switch` forms, `try`/`catch`/`finally`, `throw`, `break`, and `continue`
- configured import emission, naming policy, type maps, exception maps, and comment flags
- dependency-ordered directory translation
- structured diagnostics, confidence scoring, validation, post-LLM structural
  verification, and optional Anthropic, Gemini, or OpenAI-compatible completion
- side-by-side Java/Python review via `j2py compare`
- rule-only project assessment via `j2py doctor` with JSON/HTML reports and conservative
  config suggestions

Known gaps include:

- overload groups whose erased Python signatures collide (e.g. `int` vs `long`) and
  other ambiguous overload groups that still fall back to manual-dispatch TODOs
- complex enum static initialization beyond translated enum constant class bodies
- annotation semantics beyond syntactic metadata shells
- runtime/framework behavior (dependency injection, persistence mappings, container
  lifecycle) — j2py translates source structure, not application frameworks

For a concise statement of where j2py helps and where enterprise framework semantics
remain manual, see [docs/POSITIONING.md](docs/POSITIONING.md).

## Which surface should I use?

j2py has several user-facing surfaces, but they are one pipeline rather than separate
products:

```text
doctor -> config -> translate -> sidecars -> wire -> validate/review
```

For simple Java, start with the core translator and review output:

```bash
j2py translate Foo.java
j2py compare Foo.java Foo.py
```

For enterprise or framework-heavy migrations, use the advanced path:

```bash
j2py doctor project/
# create and review config
j2py translate project/ --config j2py_config.py --output translated_py
j2py-wire list translated_py
j2py-wire generate translated_py --target fastapi
j2py-wire validate translated_py
```

The layers are: core translator, configuration, framework plugins, wiring, and
assessment. See [Positioning and enterprise scope](docs/POSITIONING.md),
[Getting Started](docs/GETTING_STARTED.md), [Assessment](docs/DOCTOR.md), and
[Wiring](docs/WIRING.md) for the full guide.

For Spring migrators, start with the [Spring conversion guide](docs/SPRING_CONVERSION.md).
It covers the opt-in Spring config, `SpringWiringPlugin` sidecars, `j2py-wire generate`,
`j2py-wire validate`, the PetClinic smoke gate, and the corpus checks that show whether
Spring translation improved or regressed. The [Spring -> FastAPI/SQLAlchemy mapping
cookbook](docs/examples/SPRING_MAPPING_COOKBOOK.md) documents detailed
`annotation_map` recipes (controllers, DI, JPA entities, `@Transactional`),
Spring JDBC/RowMapper SQLAlchemy scaffolding, and explicit manual-port callouts. For
framework metadata extraction or source transforms beyond one-to-one mappings, see the
[framework plugin guide](docs/FRAMEWORK_PLUGINS.md).
Install `j2py-converter[spring]` only when you need the optional Spring/FastAPI/SQLAlchemy
runtime packages; installing that extra does not enable Spring behavior without explicit
configuration.

## Quick start

Install the beta pre-release from PyPI:

```bash
pip install --pre j2py-converter
j2py --help
```

The PyPI distribution is **`j2py-converter`**; the import package and CLI command are
**`j2py`**. (The bare `j2py` name on PyPI is owned by an unrelated project.)

For a full user walkthrough, start with [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).
For install variants and troubleshooting, see [docs/INSTALL.md](docs/INSTALL.md). For
command details, see [docs/CLI.md](docs/CLI.md). For the full docs map by audience, use
[docs/README.md](docs/README.md), which separates User Docs, Java enterprise framework
guides, Developer Docs, and Repo Hygiene records. For the 0.8.0 release story and current
known limits, see [docs/releases/0.8.0/RELEASE_NOTES.md](docs/releases/0.8.0/RELEASE_NOTES.md).

First installed-package smoke:

```bash
mkdir -p /tmp/j2py-smoke/src/main/java/demo
cat > /tmp/j2py-smoke/src/main/java/demo/HelloWorld.java <<'JAVA'
package demo;

public class HelloWorld {
    private final String name;

    public HelloWorld(String name) {
        this.name = name;
    }

    public String greeting() {
        return "Hello, " + name;
    }
}
JAVA

j2py translate /tmp/j2py-smoke/src/main/java \
  --output /tmp/j2py-smoke/translated_py \
  --no-llm \
  --no-validate

python -m py_compile /tmp/j2py-smoke/translated_py/demo/HelloWorld.py
```

Local development:

```bash
uv sync --locked
make check
```

Translate a file without LLM completion:

```bash
uv run j2py translate tests/fixtures/java/HelloWorld.java --no-llm --no-validate --dry-run
```

Assess a Java source tree before migration:

```bash
uv run j2py doctor path/to/java/root --json j2py-assessment.json --html j2py-assessment.html
uv run j2py doctor path/to/java/root --config-suggestions j2py.suggested.yaml
uv run j2py doctor diff before.json after.json
uv run j2py sarif j2py-assessment.json --output j2py.sarif
```

See [docs/DOCTOR.md](docs/DOCTOR.md) for the assessment layer guide, report format,
roadmap, and limitations, and [docs/SARIF.md](docs/SARIF.md) for code-scanning export.

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
uv run j2py translate SomeClass.java --no-llm --llm-review --review-report review.json
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

See [docs/OUTPUT_REVIEW.md](docs/OUTPUT_REVIEW.md) for how to interpret confidence,
warnings, validation, TODO markers, and generated review artifacts.

VS Code support is experimental beyond `j2py compare`. The repository includes a small
extension package under `packages/j2py-vscode` for editor-triggered translation,
side-by-side review, TODO diagnostics, and status-bar confidence. See
[docs/VS_CODE.md](docs/VS_CODE.md) before relying on it in a migration workflow.

LLM completion with the default Anthropic provider (requires `ANTHROPIC_API_KEY`):

```bash
ANTHROPIC_API_KEY=... uv run j2py translate SomeClass.java
```

LLM completion with Gemini Flash requires the optional Gemini extra plus
`GEMINI_API_KEY`:

```bash
pip install --pre "j2py-converter[gemini]"
GEMINI_API_KEY=... uv run j2py translate SomeClass.java \
  --llm-provider gemini --model gemini-3.5-flash
```

Selecting `--llm-provider gemini` without the extra installed fails with an install hint
instead of a raw Python import traceback. Contributor installs that use the `dev` extra
also include the Gemini SDK so live Gemini probes and harvest commands remain available.

LLM completion with OpenAI-compatible endpoints requires the optional OpenAI extra,
`OPENAI_API_KEY`, and an explicit endpoint model ID. Set `OPENAI_BASE_URL`, configure
`llm_base_url`, or pass `--llm-base-url` for non-default endpoints:

```bash
pip install --pre "j2py-converter[openai]"
OPENAI_API_KEY=... uv run j2py translate SomeClass.java \
  --llm-provider openai \
  --llm-base-url https://openai-compatible.example/v1 \
  --model provider-model-id
```

Selecting `--llm-provider openai` without the extra installed fails with an install hint.
`openai-compatible` is accepted as a config/CLI alias for `openai`.

Configuration can live in `j2py.yaml`, `j2py.toml`, `[tool.j2py]` in
`pyproject.toml`, or `j2py_config.py`. Projects may set default `llm_provider`,
`llm_base_url`, and `model` values there, while CLI flags override them for one command.
See
[docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the schema.

Programmatic callers can use the Python API described in [docs/API.md](docs/API.md);
supported imports and result models are listed in
[docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Quality gates

```bash
make check         # ruff + mypy strict + pytest (excludes behavior, live_llm, target_translation)
make test-cov      # pytest with enforced line and branch coverage floors
make test-behavior # Java/Python stdout/stderr/exit-code equivalence (requires JDK)
make equivalence-report # verified fixture surface + library-wide denominator report
make test-targets  # future strict-xfail roadmap targets
make release-check # pre-release gate: release-test + dist-check (3.11+ in CI publish workflow)
```

### Benchmark corpus

Translation quality is measured against a **multi-library corpus**: pinned checkouts of
Spring Framework, Guava, Apache Commons Lang, Jackson, and Caffeine, plus small curated
construct fixtures under `tests/fixtures/corpus/`. These libraries are open-source stress
tests for the deterministic rule layer — not product scope or target runtime.
Corpus-derived fast fixtures that should not affect committed baselines live under
`tests/fixtures/java/targets/` instead.

Corpus scores are breadth and regression signals, not enterprise-readiness claims. In
particular, `spring-dense` measures Java constructs in Spring Framework sources; it does
not mean Spring Boot, Hibernate, or Jakarta application semantics are ported. See
[docs/POSITIONING.md](docs/POSITIONING.md) and
[docs/CORPUS_SCOREBOARD.md](docs/CORPUS_SCOREBOARD.md) for how to read these metrics.

```bash
make corpus-list-presets              # show all pinned presets
make corpus-clone-all                 # one-time: clone all checkouts into .corpus/
make corpus-guava-dense-check         # Guava collect/base vs baseline
make corpus-commons-lang-dense-check  # Commons Lang utilities vs baseline
make corpus-jackson-dense-check       # Jackson databind vs baseline
make corpus-caffeine-dense-check      # Caffeine cache code vs baseline
make corpus-spring-dense-check        # Spring dense preset + construct fixtures
make corpus-spring-app-dense-check    # Spring app-layer samples (REST, JPA, @Transactional)
make corpus-petclinic-dense-check     # Spring PetClinic reference application
make test-spring-smoke                # optional translate -> sidecar -> wire -> FastAPI smoke
make corpus-hotspots                  # rank gaps across all committed baselines
```

Presets and baselines live in `scripts/corpus/corpus_presets.py` and
`tests/fixtures/corpus/`. In git worktrees, set `J2PY_CORPUS_ROOT` to your main checkout
so scripts reuse `$J2PY_CORPUS_ROOT/.corpus/`. Regenerate a baseline with
`make corpus-<name>-update-baseline` only after comparison shows no regressions.

See [docs/CORPUS_SCOREBOARD.md](docs/CORPUS_SCOREBOARD.md),
[docs/TRANSLATION_TARGETS.md](docs/TRANSLATION_TARGETS.md), and the full
[documentation index](docs/README.md), which is split into User, Developer, and Repo
Hygiene docs plus source-framework-specific guides.

On-demand live LLM evaluation and harvest (excluded from `make check`):

```bash
make test-llm-e2e              # Anthropic live probes; requires ANTHROPIC_API_KEY
make test-llm-gemini-e2e       # Gemini live probe; requires GEMINI_API_KEY
make harvest-promote-dry        # triage + draft pattern-family issues; no LLM
make harvest-promote            # queue → Gemini batch → triage → draft issues
make harvest-promote-issues     # same + gh issue create
make harvest-queue REFRESH=1    # rebuild Tier-A queue from corpus-reports/
make harvest-pipeline           # local probe harvest → triage → FUTURE_TARGETS drafts
make harvest-gemini             # batch Gemini harvest from .j2py/harvest/queue.txt
make harvest-triage             # summarize local .j2py/harvest/records.jsonl
# promote vars: LIMIT=2 ISSUES=3; harvest-gemini: OFFSET=0 LIMIT=10 SLEEP=6 FILE_LIST=...
```

Worktrees: set `J2PY_CORPUS_ROOT` to the main checkout so `.env`, queue, cache, and
`.j2py/harvest/` resolve correctly. See [docs/LLM_HARVEST.md](docs/LLM_HARVEST.md) for
queue tiers, content cache, state files, and the harvest-promote agent skill.

## Adding translation rules

For the detailed contributor workflow, start with
[docs/developer/RULE_AUTHORING.md](docs/developer/RULE_AUTHORING.md),
[docs/developer/TRANSLATION_INTERNALS.md](docs/developer/TRANSLATION_INTERNALS.md), and
[docs/developer/VALIDATION_GATES.md](docs/developer/VALIDATION_GATES.md). The short
version is:

1. Add or update a Java/Python fixture pair under `tests/fixtures/`.
2. Implement the smallest deterministic rule in `j2py/translate/`.
3. Graduate the behavior into normal tests once it passes.
4. Run `make check` and relevant corpus checks, such as `make corpus-guava-dense-check`
   for generics/collections or `make corpus-spring-dense-check` when construct-mix
   behavior may shift.
5. Update a corpus baseline only when comparison shows no regressions.

Material translation policy changes should get an ADR under `docs/decisions/`.

## Beta release notes

`j2py-converter` is published as a beta package. Expect incomplete construct
coverage, diagnostics for unsupported regions, known multi-file import limitations,
and manual review on production-scale codebases. See
[docs/releases/0.8.0/RELEASE_NOTES.md](docs/releases/0.8.0/RELEASE_NOTES.md) for the current release notes,
[docs/RELEASING.md](docs/RELEASING.md) for the release checklist, and
[CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT. See [LICENSE](LICENSE).
