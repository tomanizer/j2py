# Spring Conversion Guide

This guide explains the Spring work that landed in j2py and how to exercise it. It is
written for migration teams that want a bounded Spring MVC/JPA slice translated into
reviewable Python plus generated FastAPI wiring.

The supported claim is intentionally narrow:

```text
Spring Java source
  -> j2py translate with explicit Spring config
  -> translated Python plus *.wiring.json sidecars
  -> j2py-wire generate --target fastapi
  -> generated FastAPI routers and providers
  -> project-owned runtime shims, database/session setup, and app entrypoint
```

j2py is not a Spring container and does not silently make every Spring application
runnable. The Spring path is opt-in, sidecar-driven, and validated by the PetClinic owner
slice smoke gate.

## What Is Supported

The current Spring profile can help with:

- preserving Spring annotations as reviewable Python markers through
  `annotation_map_preset: spring`;
- lowering request-body DTO-style classes to Pydantic `BaseModel`;
- lowering Bean Validation field annotations such as `@NotNull`, `@Size`, `@Min`, and
  `@Max` to Pydantic `Field(...)` constraints where the rule layer has enough context;
- lowering JPA `@Entity` classes to SQLAlchemy declarative models for supported fields
  and relationships;
- lowering Spring Data repository interfaces to session-injected SQLAlchemy repository
  classes for supported CRUD methods;
- preserving or lowering `@Transactional` semantics as explicit Python transaction
  boundaries where supported;
- lowering `@ConfigurationProperties` classes to Pydantic settings classes;
- emitting Spring route, dependency-injection, repository, entity, settings, transaction,
  and JDBC bean topology facts through the generic `*.wiring.json` sidecar path;
- generating FastAPI `APIRouter`, `Depends(...)` providers, and app registration helpers
  with `j2py-wire`.

Runtime policy remains project-owned. Your application still supplies real session
factories, database engines, authentication, error handling, transaction management, and
production app startup code.

## Install

Default installs stay framework-neutral:

```bash
pip install --pre j2py-converter
```

Install the Spring extra only in environments that need to import or test generated
Spring/FastAPI/SQLAlchemy output:

```bash
pip install --pre "j2py-converter[spring]"
```

For local repository work:

```bash
uv sync --locked --extra spring --extra test --extra validate
```

Installing the extra does not enable Spring behavior by itself. You still need explicit
configuration.

## Configure Spring Translation

Use a trusted Python config when you need the built-in `SpringWiringPlugin`, because
plugin instances are Python objects and YAML/TOML cannot safely carry them:

```python
# j2py_config.py
from j2py.framework_plugins.spring import SpringWiringPlugin as _SpringWiringPlugin

annotation_map_preset = "spring"
framework_plugins = [_SpringWiringPlugin()]
emit_wiring_metadata = True
```

Then translate with that config:

```bash
j2py translate src/main/java \
  --config j2py_config.py \
  --output translated_py \
  --no-llm
```

Expected outputs:

```text
translated_py/
  com/example/owner_controller.py
  com/example/owner_controller.wiring.json
```

The Python file is the translated source. The `*.wiring.json` file contains structured
framework facts for downstream tooling. j2py writes sidecars through the generic
framework plugin path; the Spring plugin does not write its own format.

## Inspect Sidecars

Use `j2py-wire list` to check that sidecars were emitted and that they contain Spring
metadata:

```bash
j2py-wire list translated_py
```

Typical output:

```text
Found 1 wiring sidecar(s) with 4 element(s).
translated_py/com/example/owner_controller.py: 4 element(s)
Spring metadata elements: 4
```

If no sidecars appear, check that:

- the config was passed with `--config`;
- `emit_wiring_metadata = True`;
- `SpringWiringPlugin()` is registered;
- the translated Java source actually contains Spring annotations recognized by the
  plugin.

## Generate FastAPI Wiring

Generate target wiring from emitted sidecars:

```bash
j2py-wire generate translated_py \
  --target fastapi \
  --output translated_py/wiring
```

Generated files are marked with a header and are safe to overwrite by rerunning the
command:

```text
translated_py/wiring/
  app_wiring.py
  owner_controller_wiring.py
```

The generated router modules include:

- `APIRouter(prefix=...)` from Spring route metadata;
- dependency providers for injected constructor/field dependencies;
- route functions that call translated controller methods;
- a `get_session()` placeholder when repository providers need a SQLAlchemy session.

The generated `get_session()` placeholder is deliberately not a production session
factory. Replace or override it in your application.

## Validate Generated Wiring

Run validation after generation:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring
```

JSON output is available for CI:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring \
  --format json
```

Exit codes:

| Exit code | Meaning |
|-----------|---------|
| `0` | No findings |
| `1` | Warnings only |
| `2` | At least one error |

Common findings:

| Code | Meaning |
|------|---------|
| `missing-session-factory` | Generated wiring still has the placeholder `get_session()` function. This is expected until your app supplies a real session factory or dependency override. |
| `unresolved-import` | Generated wiring imports a translated module that is missing from the translated output root. |
| `missing-provider` | Sidecar dependency metadata exists but the generated provider is absent or was edited away. |
| `route-handler` | Route metadata points to a translated controller method that validation could not find. |
| `route-parameter` | Generated FastAPI route signature no longer matches route metadata. |
| `spring-profile` | Sidecar metadata uses an unsupported Spring profile version or invalid element shape. |

## Wire Into An Application

A minimal app can import the generated route registrar:

```python
from fastapi import FastAPI

from translated_py.wiring.app_wiring import register_routes

app = FastAPI()
register_routes(app)
```

For database-backed repositories, provide your own session dependency. In tests, FastAPI
dependency overrides are often the cleanest way to supply project runtime policy without
editing generated files:

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from translated_py.wiring import owner_controller_wiring

engine = create_engine("sqlite://")
SessionLocal = sessionmaker(bind=engine)


def get_session_override() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


app.dependency_overrides[owner_controller_wiring.get_session] = get_session_override
```

Keep this boundary explicit. j2py and `j2py-wire` produce translated code and generated
glue; your application owns runtime choices.

## PetClinic Smoke Gate

The end-to-end Spring acceptance test is optional and excluded from normal `make check`:

```bash
make test-spring-smoke
```

The smoke test translates a constrained PetClinic owner slice, writes real
`*.wiring.json` sidecars through `SpringWiringPlugin`, runs `j2py-wire generate`, runs
`j2py-wire validate`, imports the generated modules, creates an in-memory SQLite schema,
starts a FastAPI `TestClient`, and checks:

- `GET /owners` returns `200`;
- `GET /owners/{id}` returns `404` for a missing owner;
- `POST /owners` with valid JSON returns `200` or `201`.

This proves the v1 pipeline is runnable for the bounded owner slice. It is not a full
Spring MVC behavioral equivalence proof.

## Measuring Whether Spring Improved

Use the smoke test for the qualitative pipeline claim:

```bash
make test-spring-smoke
```

Use corpus checks for regression and breadth:

```bash
make corpus-spring-dense-check
make corpus-spring-app-dense-check
make corpus-petclinic-dense-check
make corpus-hotspots
```

In a git worktree, reuse corpus clones from the main checkout:

```bash
export J2PY_CORPUS_ROOT=/path/to/main/j2py
```

Interpret the signals separately:

- `make test-spring-smoke` proves the translate -> sidecar -> wire -> FastAPI smoke path
  still works.
- `make corpus-*-check` proves no regression against committed Spring/PetClinic
  baselines.
- `make corpus-hotspots` summarizes committed baseline quality and remaining gap
  clusters.

When comparing two branches, run the same commands on both and report deltas such as
average coverage, full-coverage files, unhandled files, parse failures, syntax failures,
and new or resolved unhandled reasons.

## Known Limits

The current Spring path does not provide:

- a Python Spring container;
- classpath scanning or auto-discovered plugins;
- Spring Security, authentication, or authorization;
- WebFlux/reactive semantics;
- complete JPQL or Spring Data query derivation;
- full JPA relationship behavior;
- production database/session lifecycle;
- broad behavioral equivalence for arbitrary Spring applications.

Treat generated output as a reviewable migration scaffold. Keep project-specific runtime
policy in application code or explicit shims.

## Related Docs

- [Spring extension PRD](SPRING_EXTENSION_PRD.md)
- [Spring roadmap guardrails](SPRING_ROADMAP_GUARDRAILS.md)
- [Spring wiring metadata profile](SPRING_WIRING_METADATA.md)
- [Framework plugin guide](FRAMEWORK_PLUGINS.md)
- [Spring mapping cookbook](examples/SPRING_MAPPING_COOKBOOK.md)
- [Corpus scoreboard](CORPUS_SCOREBOARD.md)
- [ADR 0024 - Spring extension boundary](decisions/0024-spring-extension-boundary.md)
- [ADR 0025 - PetClinic smoke gate](decisions/0025-petclinic-smoke-gate.md)
