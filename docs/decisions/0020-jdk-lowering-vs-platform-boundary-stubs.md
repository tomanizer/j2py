# ADR 0020 — JDK lowering vs platform boundary stubs

**Date:** 2026-06-16
**Status:** Accepted

## Context

Almost every Java codebase depends on the JDK: `java.lang.String`, `java.util` collections,
`java.time`, `java.nio.file`, and — in enterprise code — platform APIs such as `java.sql`
(JDBC), `javax.servlet`, and framework packages (`org.springframework`, `jakarta.*`).

Contributors and users ask whether j2py should “support” these libraries. The question mixes
two different goals:

1. **Structural translation** — types, imports, and call sites lower to reviewable Python
   that parses and type-checks.
2. **Runtime emulation** — translated code runs against a Python reimplementation of the
   JDK or JDBC stack.

j2py already does (1) partially via built-in maps and call shims (`j2py/config/default.py`,
`j2py/translate/expr_calls.py`) and explicitly rejects pretending unresolved Java packages
are importable Python modules (LLM system prompt, pipeline hygiene). The PRD lists full
Spring/Hibernate framework semantics as a non-goal; JDBC and other I/O boundaries raise the
same design question at a lower layer.

Without an explicit policy, work drifts toward either:

- **Over-scoping** — shipping fake `java.sql` modules or a JVM compatibility layer inside
  j2py, or
- **Under-scoping** — treating ubiquitous `String`/`List` patterns as “user problem” and
  leaving obvious, high-frequency lowering to the LLM.

We need a settled tier model so rule-layer work, harvest promotion, behavior-corpus cases,
and project `import_map` configuration all pull in the same direction.

## Decision

j2py is a **structural transposer**, not a JVM. “Supporting” a Java library means lowering
its *usage patterns* to Python equivalents — never emitting `from java.*` / `from javax.*`
imports as if the JDK were installed in Python.

Adopt a **three-tier policy** for JDK and platform APIs.

### Tier 1 — Structural JDK (core, non-negotiable)

**Scope:** Types and imports that appear in nearly every Java file.

Examples: `java.lang` primitives and boxed types, `String`, `Object`, common exceptions;
`java.util` collections, `Optional`, basic functional types; annotations that are dropped or
stubbed syntactically.

**Mechanism:**

- Built-in `type_map`, `collection_map`, `exception_map`, `literal_map`
  (`j2py/config/default.py`)
- `drop_imports` for types that map to Python builtins
- `import_map` entries for a small set of stable stdlib mappings (e.g. `java.nio.file.Path`
  → `pathlib.Path`)

**Goal:** Translated output preserves class/method structure, parses, and type-checks.
This tier is what corpus node-coverage scoreboards measure breadth over.

### Tier 2 — Deterministic call lowering (core, incremental)

**Scope:** High-frequency JDK *methods and statics* where a single, semantics-preserving
Python expression exists without a project-specific runtime.

Examples already in the rule layer: `.length()` / `.size()` → `len()`, `String.format` → `%`
formatting, `Math.abs` → `abs()`, collection `.isEmpty()` → `not x`, common `String` instance
methods (`trim`, `toLowerCase`, `startsWith`, …).

**Mechanism:**

- Rule-layer shims in `j2py/translate/expr_calls.py` (and related expression modules)
- New shims added with Java/Python fixture pairs and, when runtime behaviour is
  non-obvious, a behavior-corpus case (`docs/BEHAVIOR_CORPUS.md`)

**Goal:** Rule-layer-only translation that is **runtime-correct** on common patterns,
without LLM involvement. Priority is driven by corpus hotspots and behavior-corpus gaps —
not by reimplementing the JDK surface area.

**Explicit Tier-2 expansion candidates** (not an exhaustive commitment): remaining common
`String` methods (`charAt`, `substring`, `indexOf`), `StringBuilder`, additional
`Collections` / `Arrays` / `Objects` statics, `java.time` → `datetime` / `zoneinfo`,
further `java.nio` and `java.math` mappings.

### Tier 3 — Platform boundaries (stubs + project config, not core emulation)

**Scope:** I/O, networking, persistence, containers, and framework packages where the
correct Python target depends on the migrating project’s stack.

Examples: `java.sql.*`, `javax.sql.*`, servlets, JMS, JNDI, Spring/Hibernate/Jakarta EE,
most `org.*` / `com.*` third-party libraries.

**Mechanism:**

- **Never** emit valid-looking imports from unresolved Java FQNs (`javax.*`, `java.sql.*`,
  `org.*`, `jakarta.*`, …).
- Emit **local placeholders** for types needed in signatures: `Protocol`-shaped stubs,
  nominal placeholder classes, or `Any` with an explicit `# TODO(j2py): …` comment when no
  narrower shape is known (per LLM prompt policy and harvest `protocol-stub` promotion).
- Map exception types where a stable, project-agnostic mapping exists (e.g.
  `SQLException` → `OSError` in `exception_map`); do not invent driver or connection
  behaviour.
- **Project-owned wiring** via `j2py.yaml` / `pyproject.toml` `[tool.j2py]`:
  `import_map`, `type_map`, and optional `drop_imports` point translated call sites at the
  user’s real Python modules (SQLAlchemy, async drivers, internal `myapp.db`, etc.).

**Goal:** Reviewable, type-checkable skeletons at migration boundaries. Runtime correctness
for JDBC, HTTP, and framework semantics is the **porting project’s** responsibility, not
j2py core.

### What j2py will not build

- A Java compatibility runtime (no vendored JDBC, no “run Java stdlib from Python” layer).
- Framework semantics in core (DI, ORM mappings, servlet lifecycle) — syntactic annotation
  translation only, consistent with PRD non-goals.
- Silent wrong lowering at boundaries — prefer `__j2py_todo__()` or explicit stubs over
  guessing driver or datasource behaviour.

### Measurement alignment

| Tier | Primary gates |
|------|----------------|
| Tier 1 | Fixture suite, mypy on translated output, corpus node coverage |
| Tier 2 | Above + behavior corpus (`make test-behavior`) and graduated equivalence fixtures |
| Tier 3 | Structural verification + project config; no core runtime-equivalence claim |

## Consequences

+ Contributors have a clear rule for “belongs in `expr_calls.py`” vs “belongs in
  `import_map`” vs “harvest / LLM stub only”.
+ High-frequency JDK patterns stay in the deterministic layer, preserving the layered
  pipeline (ADR 0003) and keeping LLM harvest focused on genuine gaps (ADR 0023).
+ Enterprise migrations can wire SQL and framework types without j2py pretending to ship
  those stacks.
− Tier 2 is open-ended; prioritisation must stay data-driven (corpus hotspots, behavior
  gaps) to avoid unbounded JDK reimplementation work.
− Tier 3 output requires per-project configuration before translated code runs against real
  infrastructure — expected for any serious port.
− Some JDK types will remain `TODO(j2py)` stubs until a project maps them or a harvest
  promotion adds a shared Protocol.

## References

- [PRD — non-goals (framework semantics, idiomatic rewrite)](../PRODUCT_REQUIREMENTS.md)
- [Configuration — `type_map`, `import_map`, `exception_map`](../CONFIGURATION.md)
- [Behavior corpus — rule-layer runtime envelope](../BEHAVIOR_CORPUS.md)
- [ADR 0003 — Layered translation pipeline](0003-layered-translation-pipeline.md)
- [ADR 0014 — Equivalence differential testing](0014-equivalence-differential-testing.md)
- [ADR 0023 — LLM harvest for rule-layer backlog](0023-llm-harvest-for-rule-layer-backlog.md)
- `j2py/config/default.py` — built-in type, collection, exception, and import maps
- `j2py/translate/expr_calls.py` — JDK call lowering shims
- `j2py/llm/prompts.py` — unresolved Java import / stub policy
