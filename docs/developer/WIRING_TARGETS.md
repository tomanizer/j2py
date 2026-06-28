# Wiring Targets

Use this guide when adding or changing `j2py-wire generate --target ...`.

`j2py-wire` is post-translation app assembly. It does not translate Java source. j2py
writes framework metadata to `*.wiring.json` sidecars. `j2py-wire` uses sidecars to
generate target-stack wiring.

## Current Shape

| Area | Module |
|------|--------|
| CLI entry point | `j2py/wire/cli.py` |
| Sidecar loading | `j2py/wire/loader.py` |
| Sidecar schema | `j2py/wire/schema.py` |
| Validation framework | `j2py/wire/validation.py` |
| FastAPI target | `j2py/wire/targets/fastapi.py` |
| Plain provider target | `j2py/wire/targets/providers.py` |
| SQLAlchemy persistence target | `j2py/wire/targets/sqlalchemy.py` |
| Tests | `tests/wire/` |

The current CLI target type is `Literal["fastapi", "providers", "sqlalchemy"]`. A new
target must be added to the CLI option, generator dispatch, and validation dispatch
deliberately.

## Target Contract

A target generator should:

- accept loaded `WiringSidecar` models, not raw JSON;
- write generated files under the requested output directory;
- return the generated paths;
- include a clear generated-file header;
- keep application-owned runtime policy explicit with stubs or TODOs;
- avoid editing translated source files;
- produce deterministic output for stable diffs.

The target can consume framework-specific metadata, but it should access it through the
generic sidecar models. For Spring, `WiringElement.spring` exposes the nested Spring
profile metadata.

## Adding A Target

1. Add `j2py/wire/targets/<target>.py`.
2. Define small dataclasses for target-specific specs when useful.
3. Parse `WiringSidecar` objects into target specs.
4. Render generated files deterministically.
5. Add the target to `j2py/wire/cli.py` for `generate`.
6. Add validation checks or target-specific validation dispatch.
7. Add tests under `tests/wire/`.
8. Update [Wiring](../WIRING.md), [CLI](../CLI.md), and this guide.

Do not add a target by making the CLI branch large. Keep target-specific rendering in the
target module and keep `cli.py` as dispatch and reporting.

## Validation Checks

Generated wiring should have checks for common broken states. The FastAPI target uses
checks such as:

- unsupported sidecar profile version;
- missing generated provider;
- unresolved imports;
- route handler mismatch;
- route parameter mismatch;
- placeholder SQLAlchemy session factory;
- sidecar controller with no generated wiring file.

The SQLAlchemy target uses checks for:

- missing generated `db.py` or `persistence.py`;
- unresolved generated imports;
- translated JDBC connection placeholders that are not bound in `persistence.py`;
- generated database URL/settings policy that still needs project implementation;
- Spring `@Transactional` or transaction-manager facts that still need explicit
  project-owned SQLAlchemy transaction policy.

**Known limitation**: the SQLAlchemy target assumes a single physical datasource. All
JDBC-typed constructor parameters in a repository receive the same `Connection`. Projects
with multiple distinct `DataSource` beans that need separate engine, session, or connection
policies are not yet supported; generated provider signatures will collapse them to one
connection. Tracked in [#636](https://github.com/tomanizer/j2py/issues/636).

New targets should follow the same pattern: findings need a stable code, severity,
location, message, and fix. Use `ValidationFinding` in `j2py/wire/validation.py`.

## Tests

Add tests that prove:

- sidecars load into the expected target specs;
- generated files match expected important content;
- generation is deterministic;
- validation reports missing app-owned policy as findings, not hidden behavior;
- invalid sidecars fail with useful diagnostics.

Run:

```bash
pytest tests/wire -q
```

If the target is connected to a framework smoke path, also run that smoke target. For
Spring/FastAPI today:

```bash
make test-spring-smoke
```

## Review Checklist

- The target consumes sidecars only after schema validation.
- Generated code is deterministic and marked generated.
- Runtime policy such as sessions, auth, transactions, and secrets stays project-owned.
- `j2py-wire validate` can detect stale or incomplete generated wiring.
- Docs show `list`, `generate`, and `validate` for the new target.
