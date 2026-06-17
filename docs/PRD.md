# Product Requirements Document — j2py

## Goal

Convert a large Java codebase to Python with **line-level semantic equivalence**: the
translated Python should be reviewable against the original Java side-by-side, class by
class, method by method, with the reviewer able to verify correctness without re-learning
the logic from scratch.

## Users

- **Primary:** A developer who owns a large Java project and needs to port it to Python.
  They understand both languages but cannot manually translate tens of thousands of lines.
- **Secondary:** Reviewers (team members, auditors) who need to verify the translated
  output is correct without being Java experts.

## Status

**Beta pre-release** (`0.5.0b2` on PyPI as `j2py-converter`). The deterministic rule layer
achieves near-complete **node coverage** on pinned multi-library dense samples (see
[docs/CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md)), but **behavioral equivalence** at
library scale is still early. Corpus coverage is a rule-layer breadth signal, not an
enterprise framework-readiness claim; see [docs/POSITIONING.md](POSITIONING.md),
[ADR 0014](decisions/0014-equivalence-differential-testing.md), and
[docs/EQUIVALENCE_TESTING.md](EQUIVALENCE_TESTING.md).

## Functional requirements

### F1 — Parse any modern Java source
Accept Java 8–21 source files. Handle: generics, lambdas, streams, records, sealed
classes, text blocks, annotations, inner classes.

### F2 — Rule-based skeleton generation
Mechanically translate common Java constructs without LLM involvement. The original design
target was ~70% of a typical class; on pinned dense corpus samples the rule layer now
reaches **98–100% average node coverage** (see [AUDIT-2026-06-15](decisions/AUDIT-2026-06-15.md)).

Deterministic support includes:

- Type annotations (Java primitives/boxed/collection types → Python type hints)
- Identifier naming (camelCase → snake_case, reserved word safety)
- Literal substitution (null→None, true→True, false→False, char literals)
- Import translation and elision
- Class/interface/enum/record structure, nested types, overload dispatch (ADR 0009)
- Method signatures with return types and parameter annotations
- Control flow (if/for/while/try/switch), streams, lambdas, synchronized blocks
- Access modifier removal
- Structured diagnostics and explicit `# TODO(j2py): …` for unsupported regions

### F3 — LLM completion of the remainder
Pass the skeleton + original Java to the configured LLM provider when rule-layer coverage
< 1.0 or when a full-coverage skeleton fails syntax/type pre-validation. Anthropic is the
default provider; Gemini can be selected explicitly for Gemini Flash. Cache responses to
avoid re-translating unchanged files. Live LLM calls are excluded from normal CI
([ADR 0004](decisions/0004-claude-as-llm-backend.md),
[ADR 0017](decisions/0017-multi-provider-llm-backend.md)).

### F4 — Confidence scoring
Each translated file receives a surfaced `confidence: float` (0–1). Low-confidence output
is flagged for human review.

**Confidence is a review trust signal, not raw node coverage.** Raw rule-layer coverage
remains available as `diagnostics.coverage`, but surfaced confidence is clamped below
1.00 when parse errors occur, post-validation fails, structural verification fails, or
the deterministic rule layer emits semantic warnings via
`diagnostics.semantic_warning_count`. Semantic warnings cap surfaced confidence at 0.99
to preserve coverage ordering while avoiding a perfect-trust signal; validation or
structural failures cap it below the low-confidence review threshold at 0.79. LLM
completion does not increase confidence after the rule layer runs
([ADR 0003](decisions/0003-layered-translation-pipeline.md)).

### F5 — Validation pipeline
Each translated file is checked: syntax (`ast.parse`), lint (`ruff`), type correctness
(`mypy`). Errors are reported on `TranslationResult`; callers may pass `validate=False`.
Post-translation checks use intentionally looser rules than dev-time `make check`.

### F6 — Dependency-ordered translation
Translate leaf classes before classes that depend on them (topological sort via
networkx). Reduces forward-reference issues in type annotations. Directory translation
supports incremental state (`--incremental`) and parallel workers.

### F7 — CLI

```text
j2py translate <file|dir> [--output <path>] [--no-llm]
                         [--llm-provider <anthropic|gemini>] [--model <id>]
                         [--incremental] [--json] [--dashboard <path>] [--report <path>]
j2py analyze  <file|dir>          # inventory classes, print dependency graph
j2py compare  <file>              # side-by-side Java/Python review (VS Code or paths)
j2py watch    <dir> [--output <path>]  # incremental re-translate on file changes
```

### F8 — Layered configuration
Project-specific type mappings, import remappings, and rule overrides via `j2py.yaml`,
`j2py.toml`, `[tool.j2py]` in `pyproject.toml`, or `j2py_config.py`. Projects may also
set default LLM provider/model values there; explicit CLI flags override these defaults.
See [docs/configuration.md](configuration.md).

### F9 — Post-LLM structural verification
After LLM completion, compare Java symbols with the returned Python AST: class and method
presence plus declaration order. Structural failures feed a single LLM repair retry
([ADR 0010](decisions/0010-post-llm-structural-verification.md)).

### F10 — Regression and measurement suites
Provide measurable quality signal without live LLM in normal CI:

- **Graduated fixtures** — Java/Python pairs and graduated roadmap targets in `make check`
- **Equivalence gate** — literal-oracle differential tests on harvested library code
  (`tests/equivalence/`, Phase 1 active)
- **Behavior corpus** — JDK stdout/exit-code parity on curated programs
  (`make test-behavior`, separate CI workflow)
- **Multi-library corpus baselines** — node-coverage scoreboards over Spring, Guava,
  Commons Lang, Jackson, Caffeine (`make corpus-*-check`, `make corpus-hotspots`)

## Non-goals

- **Full-library automatic execution equivalence** — j2py does not yet prove that every
  translated method in a large external checkout matches Java on all upstream tests.
  Phased equivalence gates (hand-written behavior corpus, harvested differential tests;
  see [ADR 0014](decisions/0014-equivalence-differential-testing.md)) cover bounded
  correctness evidence; corpus scoreboards measure rule-layer breadth, not runtime output.
- **Idiomatic Python rewrite** — the output preserves Java structure. Pythonification
  (replacing getters with properties, removing unnecessary classes) is explicitly out of
  scope to keep the output reviewable against the Java.
- **Java reflection, byte manipulation, JNI** — not translatable; flagged with
  `# TODO(j2py): reflection — manual port required`.
- **Full Spring/Hibernate framework support** — annotations are translated syntactically;
  framework semantics (DI, ORM mappings) must be ported manually. JDBC and other
  platform I/O boundaries follow the same stub-plus-project-config policy
  ([ADR 0020](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md)).
- **Round-trip Java generation** — j2py is one-way.

## Success criteria

1. A class with no generics, streams, or reflection translates with rule layer only
   (0 LLM calls, confidence = 1.0).
2. `HelloWorld.java` fixture translates to the expected `HelloWorld.py` fixture exactly.
3. `mypy` passes on all translated output from the fixture suite.
4. The `j2py analyze` command correctly identifies all classes, methods, and fields in a
   200-class project in under 10 seconds.
5. `make check` passes (lint, strict mypy on `j2py/`, pytest excluding `behavior`,
   `live_llm`, and future `target_translation` xfails) — currently **2,000+** tests
   including graduated constructs, the
   CharUtils and NumberUtils literal-oracle equivalence gates.
6. Committed multi-library corpus baselines provide regression signal; CI gates every
   committed dense baseline (`spring-dense`, `guava-dense`, `commons-lang-dense`,
   `jackson-dense`, and `caffeine-dense`) against baseline drift.
7. Behavior and equivalence suites provide bounded runtime-correctness signal without
   requiring live LLM calls in normal CI.

## References

- [Architecture](ARCHITECTURE.md)
- [Audit 2026-06-17](decisions/AUDIT-2026-06-17.md)
- [Translation targets](TRANSLATION_TARGETS.md)
- [Corpus scoreboard](CORPUS_SCOREBOARD.md)
- [Equivalence testing design](EQUIVALENCE_TESTING.md)
- [JDK lowering vs platform boundaries](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md)
