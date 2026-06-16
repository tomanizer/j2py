# ADR 0019 — Annotation map framework lowering

**Date:** 2026-06-16
**Status:** Accepted

## Context

j2py preserves Java annotations for review, but framework-heavy projects need a way to
lower known annotations into project-specific Python constructs. Spring applications often
encode wiring, routes, transactions, and persistence metadata in annotations such as
`@RestController`, `@GetMapping`, `@Autowired`, `@Entity`, and `@Transactional`.

Hard-coding Spring, JPA, FastAPI, SQLAlchemy, or dependency-injection semantics in the
core translator would make j2py opinionated about runtime frameworks. That conflicts with
the product goal: deterministic, reviewable Java-to-Python structure with project policy
kept explicit and auditable.

## Decision

Add an opt-in `annotation_map` configuration table to `TranslationConfig`.

Each entry maps a Java annotation simple name or fully qualified name to explicit lowering
rules supplied by the user:

- `python_decorator` emits a configured Python decorator on classes or methods.
- `import` registers required Python imports.
- `python_base` appends a configured base class to class declarations.
- `field_comment` emits a formatted field/init-assignment review comment.
- `emit_init_param` turns an annotated instance field into a constructor parameter and
  assigns `self.<field> = <field>`.
- `drop` explicitly drops the annotation.
- `preserve_comment` controls whether the original `# @Annotation(...)` audit comment is
  kept for mapped annotations.

The mapping is strict and project-owned. j2py ships no default Spring profile. A reference
profile may live in docs or tests as an example, but users must copy/adapt it and provide
their own runtime shims.

Unmapped annotations keep the Tier 1 behavior: diagnostics plus optional line comments.
No LLM prompt should infer framework behavior for annotations that are not mapped.

## Consequences

+ Framework-heavy codebases can version annotation lowering policy with their project
  config instead of maintaining an external post-processor.
+ The generated Python remains auditable because mapping rules, imports, and diagnostics
  are explicit.
+ Core j2py remains framework-neutral.
− Flat mappings cannot express complex composition, conflict resolution, classpath
  discovery, or ORM relationship semantics. Those remain future plugin-architecture work.
− Incorrect project mappings can generate syntactically valid but semantically wrong
  Python. Review comments and mapped diagnostics are therefore preserved by default.

## References

- Issue #335 — Tier 2 `annotation_map` config for framework annotation lowering
- Issue #334 — Tier 1 annotation visibility
- Issue #333 — enterprise/Spring audit
- [docs/configuration.md](../configuration.md)
