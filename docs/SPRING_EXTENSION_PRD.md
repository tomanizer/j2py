# Spring Extension PRD

## Product framing

Spring conversion is an optional j2py extension profile. It builds on j2py's core
Java-to-Python translation pipeline, but it does not change the core mission: j2py remains
a reviewable Java source transpiler, not a Spring runtime, dependency-injection container,
or automatic FastAPI application generator.

The Spring profile is useful when a migration team wants to translate a bounded Spring
MVC/JPA/DI application slice into Python while keeping framework behavior explicit and
reviewable. Spring-specific behavior must be enabled through project configuration,
framework plugins, sidecar metadata, downstream wiring tools, optional extras, or external
project shims.

## Users

- Enterprise migration teams translating Spring applications to Python.
- Application owners who need generated code that can be reviewed against Java source.
- Reviewers and auditors who need a durable boundary between Java translation and
  target-framework policy.
- Platform teams that own FastAPI, SQLAlchemy, dependency-injection, transaction, and
  packaging conventions outside j2py core.

## Problem

Spring applications mix Java language constructs with framework semantics: MVC route
registration, request/response DTO binding, validation, persistence, repository access,
dependency injection, and transaction policy. A useful migration toolchain must preserve
the reviewable Java-to-Python correspondence while surfacing enough structured framework
facts for the target Python stack.

The risk is a hidden runtime rewrite: if Spring behavior is silently hard-coded into core
translation, reviewers cannot tell which output came from Java semantics and which came
from framework policy. The extension must make that boundary visible.

## Architecture

```text
Java Spring source
        |
        v
j2py translate
  - normal Java rule layer
  - optional annotation_map_preset: spring
  - optional FrameworkPlugin instances
  - optional *.wiring.json sidecars
        |
        v
translated Python classes plus metadata
        |
        v
j2py-wire
  - consumes sidecars
  - generates FastAPI routers, providers, and app wiring
        |
        v
bounded smoke app
```

j2py owns source translation and metadata emission. `j2py-wire` owns target application
wiring from sidecars. Optional project shims own runtime behavior such as decorators,
session factories, transaction wrappers, and FastAPI/SQLAlchemy integration.

## Existing assets

The Spring extension builds on delivered work. Future changes should extend these surfaces
rather than duplicate them:

- #522 - PetClinic corpus fixture and PetClinic corpus targets.
- #523 - `annotation_map_preset: spring` and runtime marker stubs.
- #524 - Bean Validation annotations lowered to Pydantic `Field(...)`.
- #525 - request-body DTO promotion to Pydantic models.
- #526 - JPA entity lowering to SQLAlchemy declarative models.
- #527 - Spring Data repository interface lowering.
- #531 - `@Transactional` preservation/lowering.
- #337 and [ADR 0022](decisions/0022-framework-plugin-architecture.md) - general
  framework plugin architecture.
- #409 - framework sidecar cleanup behavior.
- [Framework plugin guide](FRAMEWORK_PLUGINS.md), [configuration docs](CONFIGURATION.md),
  [Spring roadmap guardrails](SPRING_ROADMAP_GUARDRAILS.md),
  [Spring wiring metadata profile](SPRING_WIRING_METADATA.md), and
  [Spring mapping cookbook](examples/SPRING_MAPPING_COOKBOOK.md).

## V1 scope

The v1 Spring extension claim is intentionally narrow:

- Spring MVC controller route facts for a pinned owner-controller slice.
- Pydantic DTO output for request and response objects.
- SQLAlchemy entity/repository output where existing rule-layer support applies.
- Dependency-injection metadata emitted through the generic framework sidecar channel and
  the v1 [Spring wiring metadata profile](SPRING_WIRING_METADATA.md).
- `j2py-wire` generation of FastAPI/SQLAlchemy wiring from sidecars.
- PetClinic owner-slice smoke test as the end-to-end acceptance target.

The target outcome is not "any Spring app works." It is that the pinned PetClinic owner
slice can translate, emit sidecars, generate wiring, import, start, and pass selected HTTP
smoke checks.

## Install and runtime boundary

Default `j2py-converter` installs must remain framework-neutral. Spring behavior requires
explicit opt-in through one or more of:

- `annotation_map_preset: spring`;
- a trusted Python config that registers a Spring framework plugin;
- `emit_wiring_metadata = True`;
- the optional `j2py-converter[spring]` install extra for FastAPI, HTTPX, SQLAlchemy, and
  pydantic-settings runtime support, or a future separate plugin package;
- project-owned runtime shims used by generated imports;
- `j2py-wire` for FastAPI/SQLAlchemy application assembly.

Spring, FastAPI, SQLAlchemy, or shim packages must not become mandatory dependencies for
default Java translation.

## Success criteria

The Spring extension is successful for v1 when #533 passes on the pinned PetClinic owner
slice:

1. j2py translates the selected Spring source with explicit Spring configuration.
2. Spring metadata is emitted through existing `*.wiring.json` sidecars.
3. `j2py-wire generate` produces FastAPI/SQLAlchemy wiring from those sidecars.
4. `j2py-wire validate` reports no blocking wiring gaps for the smoke slice.
5. The generated smoke app imports, starts, and returns the selected HTTP responses.

Run the optional integration gate with:

```bash
make test-spring-smoke
```

This target is intentionally excluded from normal `make check` because it exercises the
Spring/FastAPI/SQLAlchemy optional dependency stack. The smoke harness validates the real
translate -> sidecar -> `j2py-wire generate` -> `j2py-wire validate` path, then supplies
project-owned FastAPI dependency overrides for the session factory and minimal HTTP 404
runtime policy.

## Non-goals

- A Python implementation of the Spring container.
- Full behavioral equivalence for arbitrary Spring applications.
- Spring WebFlux or reactive-stack support.
- Spring Security, authentication, or authorization.
- Blanket JPQL or Spring Data derived-query translation.
- Complete JPA relationship translation in v1.
- Default FastAPI, SQLAlchemy, Pydantic, or Spring behavior in core translation.
- Moving `j2py-wire` generation into `j2py translate`.
- Auto-discovery of Spring plugins or classpath-based framework detection.

## Governance

Spring-specific behavior belongs behind explicit extension seams unless it is a general
Java translation improvement. Acceptable locations are:

- `annotation_map` entries and `annotation_map_preset: spring` for marker mapping;
- `FrameworkPlugin` implementations for framework handling that needs code;
- `FrameworkTransformResult.metadata` under a Spring profile namespace;
- existing `*.wiring.json` sidecars;
- `j2py-wire`;
- optional install extras or separate plugin packages;
- project-owned shims.

Unacceptable locations are:

- default translation behavior with no Spring configuration;
- a second framework plugin API;
- a second sidecar writer or top-level sidecar shape;
- Spring-only rewrites of generic framework plugin concepts;
- mandatory runtime dependencies for the core translator.

See [ADR 0024](decisions/0024-spring-extension-boundary.md) for the architecture decision
that formalizes this boundary. See
[SPRING_ROADMAP_GUARDRAILS.md](SPRING_ROADMAP_GUARDRAILS.md) for the implementation
checklist that future Spring roadmap PRs must use.
