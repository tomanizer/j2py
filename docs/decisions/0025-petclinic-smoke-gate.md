# ADR 0025 - PetClinic smoke gate

**Date:** 2026-06-18
**Status:** Accepted

## Context

The Spring extension roadmap defines a narrow v1 claim: a constrained PetClinic owner
slice can translate through j2py, emit Spring wiring sidecars, generate FastAPI wiring
with `j2py-wire`, import, start, and pass selected HTTP smoke checks.

ADR 0024 keeps Spring conversion split across two tools. `j2py translate` owns Java source
translation and framework metadata emission. `j2py-wire` owns FastAPI router and provider
generation. Project runtime behavior, including session factories and application-specific
404 semantics, remains outside core translation.

## Decision

The v1 Spring acceptance gate is an optional pytest marker and Makefile target:

```bash
make test-spring-smoke
```

The gate translates `tests/fixtures/java/PetClinicSmokeOwnerSlice.java` with
`annotation_map_preset: spring`, `SpringWiringPlugin`, and `emit_wiring_metadata=True`.
It writes the real translated Python module and real `*.wiring.json` sidecar, runs
`j2py-wire generate --target fastapi`, runs `j2py-wire validate`, imports the generated
modules, creates an in-memory SQLite schema from the translated SQLAlchemy model, starts a
FastAPI `TestClient`, and exercises:

- `GET /owners`
- `GET /owners/{owner_id}`
- `POST /owners`

The smoke app uses FastAPI dependency overrides for the project-owned session factory and
minimal controller behavior needed to turn missing owners into HTTP 404 responses. Those
overrides do not replace the sidecar, generated router, generated providers, or generated
app registration path.

## Consequences

+ The roadmap has an executable end-to-end gate for the bounded Spring conversion claim.
+ Normal `make check` stays framework-neutral and does not require FastAPI or SQLAlchemy.
+ `j2py-wire validate` can still report the expected session-factory warning before the
  smoke app supplies its project-owned override.
- The gate is an integration smoke, not a behavioral equivalence proof for Spring MVC or
  the full official PetClinic application.
- Runtime policy remains explicit in the smoke harness until a consuming application
  supplies its own database/session and error-handling conventions.
