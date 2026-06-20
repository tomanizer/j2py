# j2py wiring

Wiring is the post-translation app assembly layer in the j2py pipeline. See
[the pipeline overview](POSITIONING.md#one-pipeline-five-layers) for how wiring fits
with assessment, configuration, translation, sidecars, validation, and review.

The translator writes reviewable Python source. Framework plugins can also extract
framework metadata from the Java source. j2py writes that metadata to sidecars.
`j2py-wire` uses sidecars to generate target-stack wiring.

That split matters. A translated controller class is still just a class until something
registers routes, creates providers, and connects dependencies. Wiring handles that
application glue without putting framework runtime policy into core translation.

## What wiring is for

Use wiring when translated Python needs target-stack assembly that does not belong inside
the class-by-class source translation:

| Need | Wiring can help with |
|---|---|
| Route registration | Generate router modules from route metadata. |
| Dependency assembly | Generate provider functions for controllers, repositories, and services. |
| App registration | Generate an `app_wiring.py` helper that mounts generated routers. |
| Review workflow | Turn sidecar metadata into Python files reviewers can inspect. |
| CI checks | Validate generated wiring and report missing providers, imports, and runtime stubs. |

Wiring is not a framework runtime. Production behavior remains project-owned:

- database engines and SQLAlchemy session factories;
- transaction policy;
- authentication and authorization;
- deployment settings and secrets;
- application startup conventions;
- error handling and HTTP response policy.

## Current support

The current implemented target is FastAPI wiring generated from translated output. For
the enterprise command path, see [Getting Started](GETTING_STARTED.md#enterprise-path).

The implemented producer is the Spring wiring metadata path:

1. `j2py translate` runs with explicit config.
2. `SpringWiringPlugin` extracts Spring route, injection, component, repository, entity, and
   JDBC bean facts where available.
3. j2py writes `*.wiring.json` sidecars when `emit_wiring_metadata = True`.
4. `j2py-wire` reads those sidecars and generates FastAPI-oriented wiring.

Future targets such as SQLAlchemy persistence, provider-only generation, and Pydantic
Settings are expected to use the same sidecar-driven shape.

## Inputs and outputs

Input:

```text
translated_py/
  owner_controller.py
  owner_controller.wiring.json
```

The Python file is the translated source. The sidecar is structured metadata about the
translated elements. For Spring, route metadata, injection metadata, component roles, and
JDBC bean facts live under `elements[].metadata.spring`.

Output:

```text
translated_py/wiring/
  owner_controller_wiring.py
  app_wiring.py
```

Generated FastAPI wiring can include:

- `APIRouter(prefix=...)`;
- route functions decorated with `@router.get(...)`, `@router.post(...)`, and related
  methods;
- provider functions such as `get_owner_repository(...)`;
- `Depends(...)` parameters;
- `register_routes(app)` in `app_wiring.py`;
- a `get_session()` placeholder when repository providers need a SQLAlchemy session.

The session placeholder is intentional. Replace or override it in project application code.

## Basic workflow

Start with translation that emits sidecars:

```python
# j2py_config.py
from j2py.framework_plugins.spring import SpringWiringPlugin as _SpringWiringPlugin

annotation_map_preset = "spring"
framework_plugins = [_SpringWiringPlugin()]
emit_wiring_metadata = True
```

```bash
j2py translate src/main/java \
  --config j2py_config.py \
  --output translated_py \
  --no-llm
```

Inspect the sidecars:

```bash
j2py-wire list translated_py
```

Generate FastAPI wiring:

```bash
j2py-wire generate translated_py \
  --target fastapi \
  --output translated_py/wiring
```

Validate the generated wiring:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring
```

For CI-friendly output:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring \
  --format json
```

## How to read validation

`j2py-wire validate` checks generated wiring against sidecars and translated modules.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | No findings. |
| `1` | Warnings only. |
| `2` | Errors. |

Common findings:

| Code | Meaning | Typical fix |
|---|---|---|
| `spring-profile` | Sidecar Spring metadata is not profile version 1 or has invalid shape. | Regenerate sidecars with the current plugin/profile. |
| `orphan-controller` | A controller sidecar has no generated wiring file. | Run `j2py-wire generate` again. |
| `unresolved-import` | Generated wiring imports a missing translated or generated module. | Check output paths and rerun generation from current translated output. |
| `missing-provider` | An injected dependency has no provider function. | Rerun generation or add a project provider. |
| `route-handler` | A route refers to a handler missing from the translated controller. | Review translated method names and sidecar metadata. |
| `route-parameter` | Generated route parameters do not match metadata. | Rerun generation and inspect parameter metadata. |
| `missing-session-factory` | Generated `get_session()` is still the j2py placeholder. | Supply a real SQLAlchemy session factory in project code. |

A `missing-session-factory` warning is expected for repository-backed wiring until the
application supplies its real session lifecycle.

## What to review

Review three artifacts together:

1. Translated Python source, for Java-to-Python correspondence.
2. `*.wiring.json` sidecars, for extracted framework facts.
3. Generated wiring files, for target-stack assembly decisions.

Good wiring output should be boring and explicit. It should show how routes and providers
are connected, where runtime placeholders remain, and which generated files are safe to
overwrite by rerunning `j2py-wire generate`.

Red flags:

- sidecars missing after translation when `emit_wiring_metadata = True`;
- sidecars containing stale paths or old profile versions;
- generated wiring importing modules that do not exist in the translated tree;
- generated providers that hide production decisions such as sessions, auth, or
  transactions;
- manual edits made directly inside generated wiring files without a plan to preserve them.

## How to test wiring

For a local migration, use this smoke loop:

```bash
j2py-wire list translated_py
j2py-wire generate translated_py \
  --target fastapi \
  --output translated_py/wiring
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring
python -m py_compile translated_py/wiring/*.py
```

If you are contributing to j2py itself, use the focused wiring tests:

```bash
uv run pytest tests/wire -q
```

For the bounded Spring/FastAPI integration smoke gate in the j2py repository:

```bash
make test-spring-smoke
```

The smoke gate exercises the real path: translate -> sidecars -> `j2py-wire generate` ->
`j2py-wire validate` -> FastAPI app smoke test.

## Related docs

- [Configuration](CONFIGURATION.md) explains `emit_wiring_metadata` and trusted Python
  plugin registration.
- [Framework plugins](FRAMEWORK_PLUGINS.md) explains how plugins extract framework metadata
  for sidecars.
- [Spring wiring metadata](SPRING_CONVERSION.md#wiring-metadata-profile) documents the Spring sidecar profile.
- [Spring conversion](SPRING_CONVERSION.md) walks through the current Spring -> FastAPI
  workflow.
- [CLI](CLI.md) is the command reference for `j2py-wire`.
