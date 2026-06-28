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
| Persistence scaffolding | Generate SQLAlchemy engine/session hooks and JDBC placeholder binding helpers. |
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

The current implemented targets are plain provider generation, SQLAlchemy persistence
scaffolding, and FastAPI wiring generated from translated output. For the enterprise
command path, see
[Getting Started](GETTING_STARTED.md#enterprise-path).

The implemented producer is the Spring wiring metadata path:

1. `j2py translate` runs with explicit config.
2. `SpringWiringPlugin` extracts Spring route, injection, component, repository, entity, and
   JDBC bean facts where available.
3. j2py writes `*.wiring.json` sidecars when `emit_wiring_metadata = True`.
4. `j2py-wire` reads those sidecars and generates provider-only, SQLAlchemy persistence,
   or FastAPI-oriented wiring.

Future targets such as Pydantic Settings are expected to use the same sidecar-driven
shape.

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
  db.py
  persistence.py
  providers.py
  owner_controller_wiring.py
  app_wiring.py
```

Generated provider wiring can include:

- plain factory functions such as `get_owner_service(...)`;
- constructor arguments derived from Spring injection metadata;
- repository factory functions that accept a caller-supplied SQLAlchemy `Session`;
- no FastAPI `Depends(...)` calls and no container runtime.

Generated FastAPI wiring can include:

- `APIRouter(prefix=...)`;
- route functions decorated with `@router.get(...)`, `@router.post(...)`, and related
  methods;
- provider functions such as `get_owner_repository(...)`;
- `Depends(...)` parameters;
- `register_routes(app)` in `app_wiring.py`;
- a `get_session()` placeholder when repository providers need a SQLAlchemy session.

The session placeholder is intentional. Replace or override it in project application code.

Generated SQLAlchemy persistence wiring can include:

- `db.py` with an explicit `Engine`, `SessionLocal`, `session_scope()`, and
  `connection_scope()` scaffold;
- recorded datasource property keys from Spring `DataSource` bean metadata;
- recorded JDBC bean topology for `DataSource`, `JdbcTemplate`,
  `NamedParameterJdbcTemplate`, and transaction-manager beans;
- `persistence.py` provider helpers that construct translated repositories with a
  caller-supplied SQLAlchemy `Connection`;
- binding for lowered JDBC placeholders such as `self.jdbc_template_connection` and
  `self.named_jdbc_template_connection`.

The generated SQLAlchemy target is still scaffolding. Replace the database URL, dialect,
pool, credentials, migrations, retry policy, and transaction semantics in project code.
When a translated repository has multiple JDBC wrapper constructor parameters such as
`JdbcTemplate` and `NamedParameterJdbcTemplate`, generated providers pass the same
SQLAlchemy `Connection` to each wrapper slot so lowered calls participate in one
transaction. Distinct physical datasource or engine policies remain project-owned.
Detected Spring `@Transactional` annotations and transaction-manager beans are surfaced as
TODOs and validation warnings; j2py does not translate rollback rules, propagation,
isolation, or read-only behavior into a hidden runtime policy.

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

Generate plain providers:

```bash
j2py-wire generate translated_py \
  --target providers \
  --output translated_py/wiring
```

Generate SQLAlchemy persistence scaffolding:

```bash
j2py-wire generate translated_py \
  --target sqlalchemy \
  --output translated_py/wiring
```

Validate the generated wiring:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring
```

Use `--target providers` to validate the generated `providers.py` module instead of
FastAPI router files. Use `--target sqlalchemy` to validate `db.py` and
`persistence.py`.

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
| `orphan-providers` | Provider sidecars exist but `providers.py` is missing. | Run `j2py-wire generate --target providers`. |
| `provider-function` | A generated provider function is missing from `providers.py`. | Rerun provider generation from current sidecars. |
| `provider-dependency` | An injection edge has no sidecar-backed provider. | Translate or define the dependency sidecar, or pass it manually. |
| `orphan-sqlalchemy-persistence` | SQLAlchemy sidecar facts exist but `db.py` or `persistence.py` is missing. | Run `j2py-wire generate --target sqlalchemy`. |
| `sqlalchemy-placeholder-binding` | A translated repository uses a JDBC connection placeholder that generated persistence wiring does not bind. | Rerun SQLAlchemy generation from current translated output. |
| `sqlalchemy-database-policy` | Generated `db.py` still uses the placeholder database URL/settings hook. | Map datasource keys to project settings and configure engine creation. |
| `sqlalchemy-transaction-policy` | Spring `@Transactional` or transaction-manager facts need explicit SQLAlchemy policy. | Implement transaction boundaries in project code. |
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
- generated SQLAlchemy files whose datasource and transaction TODOs were not replaced
  before production use;
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

For provider-only wiring, replace `--target fastapi` with `--target providers`; the
generated module remains ordinary importable Python.

For SQLAlchemy persistence scaffolding, replace `--target fastapi` with
`--target sqlalchemy`; the expected warning-only state means the generated database and
transaction policy TODOs still need project-owned implementation.

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
