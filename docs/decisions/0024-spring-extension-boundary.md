# ADR 0024 - Spring extension boundary

**Date:** 2026-06-18
**Status:** Accepted

## Context

[ADR 0022](0022-framework-plugin-architecture.md) introduced a general enterprise
framework extension point: trusted `FrameworkPlugin` instances can add reviewable output
and structured metadata, and `emit_wiring_metadata` can write versioned `*.wiring.json`
sidecars for downstream tooling.

The Spring roadmap now uses that architecture for a bounded Spring MVC/JPA/DI migration
profile. Spring support is already partly implemented through:

- `annotation_map_preset: spring` marker lowering;
- Bean Validation to Pydantic field lowering;
- request-body DTO promotion to Pydantic models;
- JPA entity lowering to SQLAlchemy models;
- Spring Data repository lowering;
- `@Transactional` preservation/lowering;
- PetClinic corpus measurement lanes.

The next roadmap stages need structured Spring wiring metadata and `j2py-wire` generation.
Without a boundary decision, those stages could accidentally turn generic framework hooks
into Spring-only APIs or move FastAPI/SQLAlchemy app assembly into `j2py translate`.

## Decision

j2py core remains a framework-neutral Java-to-Python transpiler. Spring is one optional
profile that consumes the general extension hooks from ADR 0022; it does not own those
hooks.

### Generic hooks stay generic

`FrameworkPlugin`, `FrameworkTransformResult.metadata`, `emit_wiring_metadata`, and
`*.wiring.json` remain general enterprise framework mechanisms. Their names, contracts,
and top-level sidecar shape must not become Spring-specific.

Other frameworks, including Jakarta, Micronaut, Quarkus, internal platforms, and
non-Spring enterprise frameworks, must remain plausible consumers of the same hooks.

### Spring marker lowering is not the wiring contract

`annotation_map_preset: spring` is marker lowering. It can preserve Spring annotations as
decorators, parameter markers, comments, or simple configured output, but it is not the
structured contract consumed by `j2py-wire`.

Wiring facts belong in plugin metadata emitted through the ADR 0022 sidecar path.

### Spring metadata is profile-namespaced

A Spring wiring plugin, such as the planned `SpringWiringPlugin`, must emit structured
facts under a Spring-specific metadata namespace, for example `metadata.spring`, while
preserving the generic sidecar envelope:

```json
{
  "schema_version": 1,
  "elements": [
    {
      "plugin": "spring-wiring",
      "kind": "method",
      "java_name": "findOwner",
      "python_name": "find_owner",
      "metadata": {
        "spring": {
          "route": {
            "method": "GET",
            "path": "/owners/{ownerId}"
          }
        }
      }
    }
  ]
}
```

The Spring profile can version its nested metadata schema, but it must not create a
parallel sidecar writer or replace the top-level sidecar contract. The v1 nested schema is
documented in [SPRING_CONVERSION.md#wiring-metadata-profile](../SPRING_CONVERSION.md#wiring-metadata-profile).
Implementation guardrails for later Spring roadmap PRs are tracked in
[SPRING_DESIGN.md](../SPRING_DESIGN.md).

### `j2py-wire` owns application wiring

`j2py translate` may emit translated Python classes and sidecar metadata. It must not
generate FastAPI app entrypoints, router aggregators, provider graphs, session factories,
or Spring container emulation.

`j2py-wire` consumes sidecars and generates target application wiring outside the core
translator. That split keeps source translation reviewable and keeps target-stack policy
owned by the wiring tool or project shims.

### Spring dependencies remain optional

Default j2py installs and default translation runs must not require Spring, FastAPI,
SQLAlchemy, Pydantic settings, or project-specific shim packages. Spring behavior must be
enabled explicitly through config, plugins, optional extras, separate packages, or
downstream tooling.

## Consequences

+ Future Spring metadata work can evolve a useful profile without narrowing the generic
  framework plugin architecture.
+ Reviewers can distinguish Java translation from Spring/FastAPI/SQLAlchemy policy.
+ The PetClinic smoke target can validate the full translate -> sidecar -> wire path
  without implying broad Spring behavioral equivalence.
+ Optional dependencies stay isolated from default Java-to-Python use.
- Some Spring behaviors will remain explicit manual-port or downstream-tool work even
  when a target stack could be guessed.
- Spring profile authors must maintain a nested metadata schema instead of relying on
  ad hoc generated code in the translator.

## Non-goals

- A Spring container, MVC dispatcher, transaction manager, or dependency-injection
  runtime inside j2py.
- Full Spring behavioral equivalence.
- WebFlux, Spring Security, scheduled jobs, cache semantics, or async execution in v1.
- Blanket JPQL or Spring Data derived-query translation.
- Auto-discovered Spring plugins or classpath-driven framework detection.
- A second framework plugin API or sidecar format.

## Relationship to product scope

[SPRING_DESIGN.md](../SPRING_DESIGN.md) defines the product scope and v1
success criteria. This ADR records the architectural boundary that keeps that product
scope optional and plugin/wire scoped.
