# Positioning and enterprise scope

j2py is a Java-to-Python **source translator** for producing Python that a reviewer can
audit against the original Java side by side. It is a migration accelerator, not an
automatic enterprise application migration platform.

The central promise is structural correspondence: preserve class order, method order,
control-flow shape, names, comments, diagnostics, and review clues well enough that a
human can verify and continue the port. Runtime correctness still needs project tests,
equivalence checks, and manual review.

## What j2py is for

j2py is useful when the Java being translated is mostly language-level code:

- utility classes, parsers, validators, calculators, and other isolated business logic
- DTO-like classes and data structures where framework behavior is not the primary value
- algorithm-heavy modules from larger enterprise systems
- first-pass migration scaffolding before a deliberate manual rewrite
- audit workflows where reviewers need source-to-source correspondence
- rule-layer research and fixture-driven Java-to-Python translation development

For these cases, the deterministic rule layer, corpus baselines, confidence scores,
diagnostics, and `j2py compare` can save substantial mechanical translation effort.

## What j2py is not

j2py does not convert a Spring, Hibernate, Jakarta EE, servlet, or JDBC application into a
runnable Python application.

In particular, core j2py does not implement:

- dependency injection containers or bean lifecycle behavior
- Spring MVC route registration, filters, security, or AOP proxies
- Hibernate/JPA ORM mappings, relationships, lazy loading, or persistence sessions
- transaction propagation, rollback rules, isolation levels, or container-managed sessions
- servlet/Jakarta lifecycle semantics
- a Python JDK, JDBC, or Java framework runtime

When Java source depends on those semantics, the translated Python should be treated as a
reviewable skeleton. The target application stack still has to be designed and wired by
the migration project.

## Interpreting corpus metrics

Corpus scoreboards measure deterministic rule-layer breadth. They do not prove that a
translated application is runnable or semantically equivalent.

`spring-dense` is especially easy to misread. It samples Java source from Spring
Framework and curated construct fixtures to stress-test language constructs. A high
`spring-dense` score means j2py handles many Java constructs found in Spring's codebase;
it does **not** mean Spring Boot application migration is ready.

`spring-app-dense` is a more honest enterprise signal because it samples application-layer
Spring patterns such as REST, DI, JPA, and transactions. Even there, node coverage must be
read alongside enterprise metrics such as annotation-only stubs and annotation-warning
rates. A class can have high node coverage while still requiring manual framework
mapping.

Use corpus metrics as a backlog and regression signal:

- high coverage means the rule layer recognized much of the Java syntax
- syntax success means the generated Python parses
- diagnostics and semantic warnings identify review-required regions
- behavior and equivalence tests are the stronger signal for runtime trust

## Framework annotations

j2py preserves and can lower annotations in two distinct ways.

Unmapped framework annotations are visible for review through diagnostics and optional
line comments. They do not carry framework behavior.

Mapped annotations use the opt-in `annotation_map` configuration described in
[ADR 0019](decisions/0019-annotation-map-framework-lowering.md) and
[configuration.md](configuration.md). This lets a project explicitly map known
annotations to its own Python decorators, imports, bases, comments, or constructor
parameters. j2py ships no default Spring, FastAPI, SQLAlchemy, or JPA semantics.

That boundary is intentional. An `annotation_map` entry is project policy, not a claim
that core j2py understands the source framework. More complex framework lowering belongs
in future explicit plugin or wiring layers, not in silent guesses by the translator.

## Practical migration workflow

For a framework-heavy enterprise codebase:

1. Identify framework-light modules that can be translated independently.
2. Translate with `--no-llm` first to get deterministic output and diagnostics.
3. Review with `j2py compare`.
4. Add project `type_map`, `import_map`, and `annotation_map` entries only when the target
   Python stack and shims are explicit.
5. Rebuild framework wiring in the target stack manually or through project-owned tools.
6. Back critical translated methods with behavior or equivalence tests before trusting
   them in production.

For utility/library-style Java, j2py can be a credible accelerator. For an end-to-end
Spring/Hibernate/Jakarta application migration, j2py is one component in a manual port,
not the migration tool by itself.

## Related docs

- [PRD](PRD.md) - product goals and non-goals
- [Corpus scoreboard](CORPUS_SCOREBOARD.md) - benchmark presets and metric semantics
- [Equivalence testing](EQUIVALENCE_TESTING.md) - runtime correctness strategy
- [Configuration](configuration.md) - project-owned mapping policy
- [ADR 0019](decisions/0019-annotation-map-framework-lowering.md) - annotation map
  framework lowering
- [ADR 0020](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md) - JDK and
  platform boundary policy
