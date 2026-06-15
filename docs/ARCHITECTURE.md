# Architecture — j2py

## Pipeline overview

```
Java source file(s)
        │
        ▼
┌───────────────┐
│   parse/      │  tree-sitter-java → ParsedFile (JavaNode AST + error list)
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   analyze/    │  symbols.py  → FileSymbols (ClassSymbol, MethodSymbol, FieldSymbol)
│               │  graph.py    → DiGraph (dependency edges) → topological order
└───────┬───────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│   translate/                                          │
│                                                       │
│   skeleton.py          Rule-based layer               │
│   ├── rules/types.py   Java type → Python type hint   │
│   ├── rules/naming.py  camelCase → snake_case          │
│   ├── rules/literals.py null/true/false/chars         │
│   ├── classes.py           Class declaration facade / router
│   ├── class_enums.py       Enum emission
│   ├── class_interfaces.py  Protocol (interface) emission
│   ├── class_annotations.py Annotation type emission
│   ├── class_members.py     Member index, Javadoc, static dispatch
│   ├── class_methods.py     Method/constructor emission
│   ├── class_nested.py      Nested type emission
│   ├── class_fields.py      Field extraction/emission
│   ├── class_model.py       Shared dataclasses
│   ├── name_resolution.py   Deterministic partial name binding
│   ├── statements.py        Statement facade / router
│   ├── stmt_control.py      if/for/while/do control-flow lowering
│   ├── stmt_exceptions.py   try/catch/throw and try-with-resources lowering
│   ├── stmt_switch.py       switch statement lowering and fall-through diagnostics
│   ├── stmt_sync.py         synchronized block lowering
│   ├── expressions.py       Expression facade / router
│   ├── expr_access.py       Identifiers, fields, arrays, casts, instanceof
│   ├── expr_calls.py        Method calls and Java standard-library shims
│   ├── expr_lambdas.py      Lambdas and method references
│   ├── expr_objects.py      Object and anonymous-class creation
│   ├── expr_ops.py          Operators, assignment, ternary, switch expressions
│   ├── expr_streams.py      Stream pipelines and collectors
│   └── expr_types.py        Best-effort expression type helpers
│                                                       │
│   Returns source, diagnostics, and coverage           │
└───────┬───────────────────────────────────────────────┘
        │  coverage < 1.0 or syntax/type pre-validation fails
        ▼
┌───────────────┐
│   llm/        │  Claude API (Anthropic SDK)
│               │  prompts.py  → structured system + user messages
│               │  client.py   → disk-cached, tenacity retry
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   verify/     │  post-LLM class/method presence + order checks
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   validate/   │  ast.parse → ruff check → mypy
│               │  Returns ValidationResult (ok, errors by category)
└───────┬───────┘
        │
        ▼
  Python source file
```

## Component responsibilities

### `parse/` — Java AST extraction
- Wraps `tree-sitter` + `tree-sitter-java` via `JavaNode` and `ParsedFile`
- `JavaNode` provides: `.type`, `.text`, `.location`, `.children`, `.walk()`, `.find_all()`
- Single entry point: `parse_file(path)` or `parse_source(bytes)`
- Surfaces parse errors as `ParsedFile.errors` — does not raise

### `analyze/` — Symbol table and dependency graph
- `symbols.py`: walks the AST to extract `FileSymbols` (package, imports, class list)
- Each `ClassSymbol` holds its fields, methods, superclass, and interface list
- `graph.py`: builds a `networkx.DiGraph` from class-level dependencies and produces
  a topological sort for translation order
- Does not modify the AST or produce any Python output

### `translate/` — Rule-based translation
- `skeleton.py`: orchestrates the rule layer; returns source, diagnostics, and coverage
  - `coverage = 1.0` means the rule layer handled everything; LLM is skipped
  - Also exposes structured diagnostics via `translate_skeleton_with_diagnostics`
- `classes.py` is the class-declaration facade; `class_enums.py`, `class_interfaces.py`,
  `class_annotations.py`, `class_members.py`, `class_methods.py`, and `class_nested.py`
  hold declaration-kind emitters and shared helpers.
- `statements.py` is the statement facade/router. It owns simple statement forms
  directly (for example returns, local variables, `break`, `continue`, and nested type
  declarations) and delegates larger families to focused modules:
  - `stmt_control.py`: enhanced/classic `for`, `if`, `while`, and `do-while`
  - `stmt_exceptions.py`: `try`, `try`-with-resources, `catch`, and `throw`
  - `stmt_switch.py`: switch statements, fall-through lowering, and explicit switch
    diagnostics
  - `stmt_sync.py`: synchronized-block lowering
- `expressions.py` is the expression facade/router. It owns literals, simple names for
  built-in Java node forms, and unsupported-expression TODO sentinels; focused families
  live in:
  - `expr_access.py`: identifiers, field/array access, array creation, casts, class
    literals, and `instanceof`
  - `expr_calls.py`: method invocations and Java standard-library shims
  - `expr_lambdas.py`: lambdas and method references
  - `expr_objects.py`: object construction and anonymous classes
  - `expr_ops.py`: assignment, update/unary/binary operators, ternaries, and switch
    expressions
  - `expr_streams.py`: stream pipelines and collectors
  - `expr_types.py`: best-effort expression type inference helpers
- Contributor import rule: route new statement and expression node kinds through the
  facade (`translate_statement` / `translate_expression`) so callers have one stable
  entry point and diagnostics/import side effects remain centralized. Add implementation
  helpers to the focused `stmt_*` or `expr_*` module that owns the construct family.
  Function-level (lazy) imports of private helpers from split modules should be used inside
  the facade routers to avoid circular imports; new pipeline, class, and test code should
  always call the facades.
- The rule layer is intentionally imperative today; a prior unused declarative
  selector/transform prototype was removed.
- `name_resolution.py` owns deterministic partial name binding for expression
  identifiers. `skeleton.py` builds file-level `FileNameBindings` from the current
  file, config import maps, package name, compilation-unit types, and static imports;
  `TranslationContext` carries a `NameResolver`; `expr_access.py` asks the resolver
  for each identifier and records required generated imports through
  `TranslationDiagnostics.imports` only when a referenced binding is emitted.
  This is intentionally not a full Java compiler resolver: it does not expand
  wildcard imports, inspect project-wide symbols, or resolve classpaths. See ADR 0016.
- `rules/`: mapping tables and stateless translation functions
  - `types.py`: recursive generic type translation (`List<Map<K,V>>` → `dict[K, V]`)
  - `naming.py`: `camel_to_snake`, `safe_identifier`, reserved-word collision handling
  - `literals.py`: literal token normalisation

### `llm/` — LLM completion
- Called when `skeleton.py` coverage < 1.0, or when a full-coverage skeleton fails
  syntax/type pre-validation
- `prompts.py`: builds a structured prompt with the Java source, partial skeleton, and
  project context plus rule diagnostics; output is plain Python source (no markdown
  fences)
- `client.py`: Anthropic SDK wrapper with API-key preflight; disk-cached at
  `~/.cache/j2py/llm/`; cache keys include prompt version, file hashes, model, config
  fingerprint, diagnostics, and validation feedback; 3 retries with exponential
  back-off via `tenacity`

### `verify/` — Structural verification
- Runs after LLM completion and compares Java symbols with the returned Python AST
- Checks class and method presence plus declaration order; constructors map to `__init__`
- Structural failures are stored on `TranslationResult` and fed into the single LLM retry

### `validate/` — Output validation
- `checks.py`: three-stage check: syntax → ruff → mypy
- Returns `ValidationResult`; never raises; errors are collected, not thrown
- Exposed on `TranslationResult` by default; callers can pass `validate=False`

### `config/` — Layered configuration
- `default.py`: canonical type, collection, exception, import, and literal maps
- `loader.py`: `ConfigLoader` stacks multiple config files (later layers override earlier
  ones for scalars; dicts and sets are merged)
- `TranslationConfig`: Pydantic model; all translation stages accept this as `cfg`

### `pipeline.py` — Orchestrator
- `translate_file(path, cfg, use_llm, model, validate) → TranslationResult`
- `translate_directory(source_root, output_root, cfg, use_llm, model, validate) →
  DirectoryTranslationResult`
- Calls parse → analyze → skeleton → (optionally) LLM with post-LLM verification →
  validation
- Directory mode builds the dependency graph and translates files in dependency order

### `cli/` — User interface
- `typer`-based CLI; `j2py translate`, `j2py analyze`, and `j2py compare`
- All output via `rich`; directory translation reports order, per-file confidence,
  diagnostics counts, validation status, and cycle warnings
- `compare` is a single-file review shortcut that reuses an existing Python file or
  generates one through the normal file pipeline, then opens an editor diff command

## Key design decisions

See [docs/decisions/](decisions/) for full ADR context.

| Decision | ADR |
|---|---|
| tree-sitter for parsing | [ADR 0002](decisions/0002-tree-sitter-for-java-parsing.md) |
| Layered rule → LLM pipeline | [ADR 0003](decisions/0003-layered-translation-pipeline.md) |
| Claude (Anthropic) as LLM backend | [ADR 0004](decisions/0004-claude-as-llm-backend.md) |
| Python 3.11+ output with type hints | [ADR 0005](decisions/0005-python-311-target-with-type-hints.md) |
| Overload translation policy | [ADR 0006](decisions/0006-overload-translation-policy.md), [ADR 0009](decisions/0009-two-tier-overload-translation.md), [ADR 0013](decisions/0013-static-overload-dispatch.md) |
| Type declaration translation | [ADR 0007](decisions/0007-type-declaration-translation.md) |
| Post-LLM structural verification | [ADR 0010](decisions/0010-post-llm-structural-verification.md) |
| Javadoc docstring translation | [ADR 0011](decisions/0011-javadoc-docstring-translation.md) |
| Sealed type metadata | [ADR 0012](decisions/0012-sealed-type-metadata.md) |
| Equivalence verification (differential testing) | [ADR 0014](decisions/0014-equivalence-differential-testing.md) |
| `synchronized(this)` translation | [ADR 0015](decisions/0015-synchronized-this-translation.md) |
| Class-reference expression imports | [ADR 0016](decisions/0016-class-reference-expression-imports.md) |

## Quality measurement

j2py uses layered gates — none of them alone proves full semantic equivalence on arbitrary
codebases, but together they cover breadth, triage, and bounded correctness.

| Layer | What it measures | How to run |
|-------|------------------|------------|
| Fixture + target tests | Exact expected output for curated Java constructs | `make check`, `make test-targets` |
| Multi-library corpus baselines | Rule-layer coverage, syntax validity, unhandled nodes on pinned library samples | `make corpus-<name>-check`, `make corpus-hotspots` |
| Behavior equivalence | stdout/stderr/exit-code match on small hand-written programs | `make test-behavior` (JDK required) |
| Harvested equivalence (phased) | Method-level Java-vs-Python differential tests with JVM-independent oracles | `tests/equivalence/` (see [EQUIVALENCE_TESTING.md](EQUIVALENCE_TESTING.md)) |

Corpus presets and baselines: [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md). CI runs a
dense-baseline matrix for every committed dense preset plus a committed-baseline hotspot
scorecard; contributors run the most relevant library checks locally for fast feedback
before pushing rule-layer PRs.

## Dependency rules

- `parse/` has no imports from other j2py packages
- `analyze/` imports `parse/` only
- `translate/` imports `parse/`, `analyze/`, `config/`
- `llm/` has no parse/analyze/translate imports; pipeline passes context into it
- `verify/` imports `analyze/` symbols and pure naming helpers only
- `validate/` imports nothing from j2py
- `pipeline.py` is the single place that imports across all stages
- `cli/` imports `pipeline.py` and `config/` only

These rules keep each stage independently testable.
