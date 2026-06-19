# Positioning and enterprise scope

j2py is a Java-to-Python **source translator** for producing Python that a reviewer can
audit against the original Java side by side. It is a migration accelerator, not an
automatic enterprise application migration platform.

The central promise is structural correspondence: preserve class order, method order,
control-flow shape, names, comments, diagnostics, and review clues well enough that a
human can verify and continue the port. Runtime correctness still needs project tests,
equivalence checks, and manual review.

## One pipeline, five layers

j2py now has several user-facing surfaces. They are not five separate products; they are
layers in one migration pipeline.

| Layer | Purpose | User-facing surface |
|---|---|---|
| Core translator | Java source -> reviewable Python | `j2py translate`, `j2py compare`, rule layer |
| Configuration | Project policy for names, imports, types, annotations, and LLM behavior | `j2py.toml`, `j2py_config.py`, `annotation_map`, `type_map`, `import_map` |
| Framework plugins | Trusted opt-in extraction of framework metadata | `framework_plugins`, `SpringWiringPlugin`, sidecar metadata |
| Wiring | Post-translation app assembly from sidecars | `j2py-wire list`, `j2py-wire generate`, `j2py-wire validate` |
| Assessment | Diagnose project readiness and migration risk | `j2py doctor`, corpus reports, diagnostics |

The full enterprise pipeline is:

```text
doctor -> config -> translate -> sidecars -> wire -> validate/review
```

Most users do not need every layer for every task. For simple Java, start with only the
core translator and review tools:

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

j2py does not convert a Spring, Hibernate, Jakarta EE, Servlet, or JDBC application into a
runnable Python application.

In particular, core j2py does not implement:

- dependency injection containers or bean lifecycle behavior
- Spring MVC route registration, filters, security, or AOP proxies
- Hibernate/JPA ORM mappings, relationships, lazy loading, or persistence sessions
- transaction propagation, rollback rules, isolation levels, or container-managed sessions
- Servlet/Jakarta lifecycle semantics
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

j2py preserves annotations and can translate them in two distinct ways.

Unmapped framework annotations are visible for review through diagnostics and optional
line comments. They do not carry framework behavior.

Mapped annotations use the opt-in `annotation_map` configuration described in
[ADR 0019](decisions/0019-annotation-map-framework-lowering.md) and
[CONFIGURATION.md](CONFIGURATION.md). This lets a project explicitly map known
annotations to its own Python decorators, imports, bases, comments, or constructor
parameters. j2py also ships an explicit `annotation_map_preset: spring` convenience map
for no-op marker decorators, but it is not enabled by default and does not implement
Spring, FastAPI, SQLAlchemy, or JPA runtime semantics.

That boundary is intentional. An `annotation_map` entry is project policy, not a claim
that core j2py understands the source framework. More complex framework metadata
extraction or source transforms belong in explicit plugin or wiring layers such as
`framework_plugins` and `j2py-wire`, not in silent guesses by the translator.

## Sidecars and wiring

For framework-heavy code, trusted framework plugins can emit structured `*.wiring.json`
sidecars. j2py writes that metadata to sidecars. `j2py-wire` uses sidecars to generate
target-stack wiring. These sidecars are review artifacts, not a second translated module
and not executable runtime behavior by themselves.

`j2py-wire` is the sibling CLI for generating or validating target-stack scaffolding. The
current implemented target is FastAPI wiring from Spring metadata.

This still does not make core j2py a Spring, FastAPI, SQLAlchemy, or dependency-injection
runtime. Generated wiring is migration scaffolding. Production runtime policy such as
database URLs, session factories, transaction boundaries, authentication, deployment
configuration, and secrets remains project-owned application code.

## Practical migration workflow

For a framework-heavy enterprise codebase:

1. Identify framework-light modules that can be translated independently.
2. Translate with `--no-llm` first to get deterministic output and diagnostics.
3. Review with `j2py compare`.
4. Add project `type_map`, `import_map`, and `annotation_map` entries only when the target
   Python stack and shims are explicit. Use `annotation_map_preset: spring` only when
   no-op Spring marker output is useful to the review workflow.
5. When configured framework plugins emit sidecars, inspect them and use `j2py-wire` or
   project-owned tools to generate reviewable target-stack wiring.
6. Back critical translated methods with behavior or equivalence tests before trusting
   them in production.

For utility/library-style Java, j2py can be a credible accelerator. For an end-to-end
Spring/Hibernate/Jakarta application migration, j2py is one component in a manual port,
not the migration tool by itself.

## Related docs

- [PRD](PRODUCT_REQUIREMENTS.md) - product goals and non-goals
- [Corpus scoreboard](CORPUS_SCOREBOARD.md) - benchmark presets and metric semantics
- [Equivalence testing](EQUIVALENCE_TESTING.md) - runtime correctness strategy
- [CLI](CLI.md) - `j2py` and `j2py-wire` command reference
- [Assessment](ASSESSMENT.md) - readiness and risk diagnosis with `j2py doctor`
- [Configuration](CONFIGURATION.md) - project-owned mapping policy
- [Framework plugins](FRAMEWORK_PLUGINS.md) - trusted plugin and sidecar extension point
- [Wiring](WIRING.md) - post-translation sidecar-to-target-stack app assembly
- [Spring conversion](SPRING_CONVERSION.md) - bounded Spring sidecar and `j2py-wire`
  workflow
- [Spring wiring metadata](SPRING_WIRING_METADATA.md) - Spring profile stored in generic
  sidecars
- [Case study](CASE_STUDY_COMMONS_LANG_TUPLE.md) - end-to-end multi-file translation case study and gap
  analysis
- [ADR 0019](decisions/0019-annotation-map-framework-lowering.md) - annotation map
  framework translation policy
- [ADR 0020](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md) - JDK and
  platform boundary policy
- [ADR 0024](decisions/0024-spring-extension-boundary.md) - Spring extension and
  `j2py-wire` boundary
