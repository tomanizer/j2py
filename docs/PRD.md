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

## Functional requirements

### F1 — Parse any modern Java source
Accept Java 8–21 source files. Handle: generics, lambdas, streams, records, sealed
classes, text blocks, annotations, inner classes.

### F2 — Rule-based skeleton generation
Mechanically translate ~70% of a typical class without LLM involvement:
- Type annotations (Java primitives/boxed/collection types → Python type hints)
- Identifier naming (camelCase → snake_case, reserved word safety)
- Literal substitution (null→None, true→True, false→False, char literals)
- Import translation and elision
- Class/interface/enum structure
- Method signatures with return types and parameter annotations
- Control flow skeleton (if/for/while/try blocks, brace→indent)
- Access modifier removal

### F3 — LLM completion of the remainder
Pass the skeleton + original Java to Claude for logic completion. Cache responses to
avoid re-translating unchanged files.

### F4 — Confidence scoring
Each translated file receives a `confidence: float` (0–1). Low-confidence output is
flagged for human review. Confidence reflects the fraction translated by the rule layer
vs. LLM.

### F5 — Validation pipeline
Each translated file is checked: syntax (ast.parse), lint (ruff), type correctness
(mypy). Errors are reported without blocking output.

### F6 — Dependency-ordered translation
Translate leaf classes before classes that depend on them (topological sort via
networkx). Reduces forward-reference issues in type annotations.

### F7 — CLI
```
j2py translate <file|dir> [--output <path>] [--no-llm] [--model <id>]
j2py analyze  <file|dir>          # inventory classes, print dependency graph
```

### F8 — Layered configuration
Project-specific type mappings, import remappings, and rule overrides via config files
layered on top of defaults.

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
  framework semantics (DI, ORM mappings) must be ported manually.
- **Round-trip Java generation** — j2py is one-way.

## Success criteria

1. A class with no generics, streams, or reflection translates with rule layer only
   (0 LLM calls, confidence = 1.0).
2. `HelloWorld.java` fixture translates to the expected `HelloWorld.py` fixture exactly.
3. `mypy` passes on all translated output from the fixture suite.
4. The `j2py analyze` command correctly identifies all classes, methods, and fields in a
   200-class project in under 10 seconds.
5. Committed multi-library corpus baselines and the behavior/equivalence suites provide
   measurable regression signal without requiring live LLM calls in CI.
