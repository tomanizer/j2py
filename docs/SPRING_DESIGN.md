# Spring design

Spring conversion is an optional j2py extension profile. It builds on the core
Java-to-Python translation pipeline, but it does not change the core mission: j2py remains
a reviewable Java source transpiler, not a Spring runtime, dependency-injection
container, or automatic FastAPI application generator. The top-level product scope stays
in [Product requirements](PRODUCT_REQUIREMENTS.md).

Spring-specific behavior must be enabled through project configuration, framework
plugins, sidecar metadata, downstream wiring tools, optional extras, or external project
shims. [ADR 0024](decisions/0024-spring-extension-boundary.md) records the architecture
decision that keeps this work optional and plugin/wire scoped.

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
reviewable Java-to-Python correspondence while surfacing enough structured framework facts
for the target Python stack.

The risk is a hidden runtime rewrite. If Spring behavior is silently hard-coded into core
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

Future changes should extend these delivered surfaces rather than duplicate them:

- #522 - PetClinic corpus fixture and PetClinic corpus targets.
- #523 - `annotation_map_preset: spring` and runtime marker stubs.
- #524 - Bean Validation annotations lowered to Pydantic `Field(...)`.
- #525 - request-body DTO promotion to Pydantic models.
- #526 - JPA entity lowering to SQLAlchemy declarative models.
- #527 - Spring Data repository interface lowering.
- #531 - `@Transactional` preservation/lowering.
- #532 - `@ConfigurationProperties` lowering.
- #544 - Spring wiring metadata profile under `elements[].metadata.spring`.
- #337 and [ADR 0022](decisions/0022-framework-plugin-architecture.md) - general
  framework plugin architecture.
- #409 - framework sidecar cleanup behavior.

Implementation should start by inspecting these surfaces:

- `j2py/config/default.py` - `SPRING_ANNOTATION_MAP` and marker-lowering defaults.
- `j2py/config/loader.py` - `annotation_map_preset`, `framework_plugins`, and
  `emit_wiring_metadata`.
- `j2py/framework.py` - public `FrameworkPlugin` and `FrameworkTransformResult`
  contracts.
- `j2py/translate/framework_dispatch.py` - guarded plugin dispatch, metadata recording,
  and Tier 2 fallback.
- `j2py/pipeline.py` - `wiring_metadata_payload()` and
  `write_wiring_metadata_sidecar()`.
- `j2py/translate/bean_validation.py` - Bean Validation to Pydantic field lowering.
- `j2py/translate/spring_model.py` - Spring/Jackson DTO detection.
- `j2py/translate/sqlalchemy_model.py` - JPA entity to SQLAlchemy lowering.
- `j2py/translate/spring_repository.py` - Spring Data repository lowering.
- `j2py/translate/spring_settings.py` - Spring `@ConfigurationProperties` lowering.
- `j2py/translate/framework_annotations.py` - annotation visibility and configured
  marker mapping.
- `docs/FRAMEWORK_PLUGINS.md`, `docs/CONFIGURATION.md`, `docs/SPRING_CONVERSION.md`,
  and `docs/examples/SPRING_MAPPING_COOKBOOK.md`.
- `tests/fixtures/framework/reference_plugin.py`, `tests/test_pipeline.py`,
  `tests/test_spring_wiring_metadata_profile.py`,
  `tests/translate/skeleton/test_annotation_visibility.py`, and
  `tests/translate/skeleton/test_fields_enums.py`.
- `tests/fixtures/corpus/petclinic-baseline.json` and existing PetClinic corpus targets.

## V1 scope

The v1 Spring extension claim is intentionally narrow:

- Spring MVC controller route facts for a pinned owner-controller slice.
- Pydantic DTO output for request and response objects.
- SQLAlchemy entity/repository output where existing rule-layer support applies.
- Dependency-injection metadata emitted through the generic framework sidecar channel and
  the v1 Spring wiring metadata profile in
  [Spring conversion](SPRING_CONVERSION.md#wiring-metadata-profile).
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

The Spring extension is successful for v1 when the pinned PetClinic owner slice satisfies
the smoke target:

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

## Required rules

Spring roadmap PRs must follow these rules:

1. Core Java-language translation may improve shared Java constructs only when the
   behavior is not Spring-specific.
2. Spring-specific annotation interpretation must be explicit through
   `annotation_map_preset: spring`, project `annotation_map`, a trusted
   `FrameworkPlugin`, or downstream wiring tooling.
3. Spring-specific structured facts must be emitted through
   `FrameworkTransformResult.metadata` and the existing `*.wiring.json` sidecar path.
4. `FrameworkPlugin`, `FrameworkTransformResult.metadata`, `emit_wiring_metadata`, and
   `*.wiring.json` must stay generic enterprise-framework hooks.
5. `j2py translate` must not generate FastAPI app entrypoints, router aggregators,
   provider graphs, session factories, or Spring container emulation.
6. `j2py-wire` owns FastAPI/SQLAlchemy application assembly from sidecars.
7. Spring/FastAPI/SQLAlchemy/Pydantic-settings dependencies must remain optional unless
   they are already core dependencies for non-Spring translation. In this distribution,
   that boundary is the `j2py-converter[spring]` / `uv sync --extra spring` extra.
8. Default `j2py translate` with no Spring config must not emit Spring marker imports,
   Spring wiring sidecars, FastAPI code, SQLAlchemy setup, or framework plugin metadata.
9. Spring tests in `make check` should stay small and fixture-focused. PetClinic and
   full translate -> wire -> smoke flows belong in optional corpus/integration gates.
10. User-facing docs must distinguish general Java transpilation, Spring marker mapping,
    rule-layer Spring translations, Spring wiring metadata, generated FastAPI wiring, and
    smoke-test scope.

## Do not duplicate

Do not create:

- another Spring annotation preset to replace `annotation_map_preset: spring`;
- another sidecar writer or top-level JSON shape;
- another framework plugin API;
- Spring-specific names for generic plugin/sidecar APIs;
- another PetClinic corpus lane;
- duplicate Bean Validation, DTO, JPA, repository, transactional, or settings
  translators;
- FastAPI/SQLAlchemy bootstrap generation inside `j2py translate`;
- mandatory Spring/FastAPI/SQLAlchemy dependencies for default j2py users.

## Review checklist

Every Spring roadmap PR should answer:

- Which existing Spring surface does this extend?
- Does it duplicate any delivered Spring work from #522-#527, #531, #532, or #544?
- Does it preserve framework plugins and sidecars as generic enterprise hooks?
- Does it change default translation with no Spring config?
- Does it introduce mandatory Spring/FastAPI/SQLAlchemy/Pydantic-settings dependencies?
- Is Spring behavior reachable only through config, plugins, sidecars, optional extras, or
  `j2py-wire`?
- Does it use the existing sidecar writer rather than a parallel format?
- Are generic translator changes justified as Java-language improvements rather than
  Spring policy?
- Are docs clear that j2py is not a Spring runtime emulator?

## Issue routing

Use these guardrails before implementing:

- #544 - metadata profile changes must stay inside the existing generic sidecar envelope.
- #545 - `SpringWiringPlugin` must be an opt-in `FrameworkPlugin` producer.
- #546 - PetClinic wiring fixtures must prove real sidecars without creating a second
  corpus lane.
- #548 - packaging must keep Spring dependencies optional and default imports clean.
- #528, #529, #530 - `j2py-wire` consumes sidecars and owns generated app wiring.
- #533 - the smoke test validates the bounded translate -> sidecar -> wire path; it is not
  a broad Spring equivalence claim.
- #534 - the epic tracks this optional extension without changing j2py's core mission.

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

## Related docs

- [Spring conversion](SPRING_CONVERSION.md) - user workflow and metadata profile.
- [Spring mapping cookbook](examples/SPRING_MAPPING_COOKBOOK.md) - recipes and manual
  port boundaries.
- [Framework plugin guide](FRAMEWORK_PLUGINS.md) - trusted plugin extension point.
- [Configuration](CONFIGURATION.md) - project-owned mapping policy.
- [ADR 0024](decisions/0024-spring-extension-boundary.md) - Spring extension boundary.
