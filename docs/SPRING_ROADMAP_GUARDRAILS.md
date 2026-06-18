# Spring Roadmap Guardrails

This document is the implementation checklist for Spring roadmap work. It complements the
product scope in [SPRING_EXTENSION_PRD.md](SPRING_EXTENSION_PRD.md), the architectural
boundary in [ADR 0024](decisions/0024-spring-extension-boundary.md), and the sidecar
profile in [SPRING_WIRING_METADATA.md](SPRING_WIRING_METADATA.md).

The rule is simple: j2py core remains a framework-neutral Java-to-Python transpiler.
Spring is an optional profile that consumes generic extension hooks; it does not own those
hooks and it does not change default translation.

## Existing Surfaces To Extend

Future Spring work should start by inspecting these surfaces and extending them when the
capability already exists:

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
  marker lowering.
- `docs/FRAMEWORK_PLUGINS.md`, `docs/configuration.md`,
  `docs/SPRING_WIRING_METADATA.md`, and `docs/examples/SPRING_MAPPING_COOKBOOK.md`.
- `tests/fixtures/framework/reference_plugin.py`, `tests/test_pipeline.py`,
  `tests/test_spring_wiring_metadata_profile.py`,
  `tests/translate/skeleton/test_annotation_visibility.py`, and
  `tests/translate/skeleton/test_fields_enums.py`.
- `tests/fixtures/corpus/petclinic-baseline.json` and existing PetClinic corpus targets.

Delivered Spring issues to preserve rather than duplicate:

- #522 - PetClinic corpus fixture and corpus targets.
- #523 - `annotation_map_preset: spring` and runtime marker stubs.
- #524 - Bean Validation annotations lowered to Pydantic `Field(...)`.
- #525 - request-body DTO promotion to Pydantic models.
- #526 - JPA entity lowering to SQLAlchemy declarative models.
- #527 - Spring Data repository interface lowering.
- #531 - `@Transactional` preservation/lowering.
- #532 - `@ConfigurationProperties` lowering.
- #544 - Spring wiring metadata profile under `elements[].metadata.spring`.

## Required Rules

Spring roadmap PRs must follow these rules:

1. Core Java-language translation may improve shared Java constructs only when the
   behavior is not Spring-specific.
2. Spring-specific annotation interpretation must be explicit through
   `annotation_map_preset: spring`, project `annotation_map`, a trusted `FrameworkPlugin`,
   or downstream wiring tooling.
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
10. User-facing docs must distinguish general Java transpilation, Spring marker lowering,
    rule-layer Spring translations, Spring wiring metadata, generated FastAPI wiring, and
    smoke-test scope.

## Do Not Duplicate

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

## Review Checklist

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

## Issue Routing

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
