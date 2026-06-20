# 0.7.0 release docs audit

This page records the release-facing documentation audit for 0.7.0. It is a checkpoint,
not a new product contract: the authoritative behavior remains the live CLI, config
schema, checked-in fixtures, and generated output.

## Scope

The audit covered:

- `README.md`
- `docs/INSTALL.md`
- `docs/GETTING_STARTED.md`
- `docs/CLI.md`
- `docs/CONFIGURATION.md`
- `docs/SPRING_CONVERSION.md`
- `docs/examples/SPRING_MAPPING_COOKBOOK.md`
- `docs/FRAMEWORK_PLUGINS.md`
- `docs/SPRING_CONVERSION.md#wiring-metadata-profile`
- `docs/POSITIONING.md`
- `docs/PRODUCT_REQUIREMENTS.md`

## Verified command surface

The documented CLI surface was checked against live help from the repository environment:

```bash
.venv/bin/j2py --help
.venv/bin/j2py translate --help
.venv/bin/j2py analyze --help
.venv/bin/j2py compare --help
.venv/bin/j2py watch --help
.venv/bin/j2py dashboard --help
.venv/bin/j2py doctor --help
.venv/bin/j2py sarif --help
.venv/bin/j2py-wire --help
.venv/bin/j2py-wire list --help
.venv/bin/j2py-wire generate --help
.venv/bin/j2py-wire validate --help
```

The checked `j2py-wire` contract is:

- commands: `list`, `generate`, and `validate`;
- target: `fastapi`;
- generated wiring default output directory: `wiring`;
- validation formats: `text` and `json`;
- validation exit codes: `0` for clean, `1` for warnings only, `2` for errors.

## Verified config contract

The docs were checked against `TranslationConfig` in `j2py/config/loader.py`.

Important release-facing boundaries:

- Spring behavior is never enabled by default.
- `annotation_map_preset: spring` is explicit opt-in marker lowering.
- `framework_plugins` accepts trusted Python plugin objects and therefore requires a
  trusted Python config file.
- YAML, TOML, and `pyproject.toml` can set scalar and mapping config, including
  `emit_wiring_metadata`, but they cannot carry plugin instances.
- Python config files are not auto-discovered; pass them explicitly with `--config`.
- Imported plugin classes in Python config should use private aliases so the loader does
  not treat them as public config keys.

## Verified generated output

Representative fixture output was regenerated with rule-only translation:

```bash
.venv/bin/j2py translate tests/fixtures/java/JdbcTemplateSqlAlchemyScaffold.java \
  --output /private/tmp/j2py-doc-audit/jdbc_template_sqlalchemy.py \
  --no-llm --no-validate

.venv/bin/j2py translate tests/fixtures/java/JdbcRowMapperScaffold.java \
  --output /private/tmp/j2py-doc-audit/jdbc_row_mapper.py \
  --no-llm --no-validate

.venv/bin/j2py translate tests/fixtures/java/SpringJdbcConfiguration.java \
  --config tests/fixtures/framework/spring_wiring_plugin_config.py \
  --output /private/tmp/j2py-doc-audit/spring_jdbc_configuration.py \
  --no-llm --no-validate

.venv/bin/j2py translate tests/fixtures/java/SpringWiringController.java \
  --config tests/fixtures/framework/spring_wiring_plugin_config.py \
  --output /private/tmp/j2py-doc-audit/spring_wiring_controller.py \
  --no-llm --no-validate
```

Observed contract:

- Simple `JdbcTemplate` and `NamedParameterJdbcTemplate` calls lower to SQLAlchemy Core
  scaffolding using `text(...)`, positional placeholder rewriting, parameter maps, and
  `.rowcount`, `.scalar_one()`, or `.mappings().one()`.
- Supported RowMapper shapes lower to row-mapping expressions or `Owner(**dict(row))`.
- Method-reference and callback-style RowMapper cases remain explicit
  `TODO(j2py): JdbcTemplate RowMapper/callback requires manual mapper port; lower to
  SQLAlchemy row mapping or a project DB facade` work.
- `SpringWiringPlugin` emits generic `*.wiring.json` sidecars with Spring facts nested
  under `elements[].metadata.spring`.
- JDBC bean metadata records `DataSource`, `JdbcTemplate`, and
  `NamedParameterJdbcTemplate` topology, including visible datasource property keys.

The generated sidecars were then exercised through `j2py-wire`:

```bash
.venv/bin/j2py-wire list /private/tmp/j2py-doc-audit
.venv/bin/j2py-wire generate /private/tmp/j2py-doc-audit \
  --target fastapi \
  --output /private/tmp/j2py-doc-audit/wiring
.venv/bin/j2py-wire validate /private/tmp/j2py-doc-audit \
  --target fastapi \
  --wiring-dir /private/tmp/j2py-doc-audit/wiring \
  --format json
```

The validation result for this focused fixture path was warnings-only:
`missing-session-factory`. That is the expected project-owned runtime boundary, not a
translation failure.

## Consistency checklist

- `docs/SPRING_CONVERSION.md` is the Spring entry point for users.
- `docs/examples/SPRING_MAPPING_COOKBOOK.md` remains the lower-level support matrix and
  example catalog.
- `README.md`, the Spring guide, the cookbook, the framework plugin guide, and the Spring
  wiring metadata profile all describe the same opt-in Spring path.
- No release-facing doc should describe all RowMapper cases as unsupported. The supported
  position is partial deterministic RowMapper lowering with explicit TODOs for callback
  and application-policy cases.
- No release-facing doc should imply default Spring, FastAPI, SQLAlchemy, JPA, or JDBC
  runtime behavior. Those paths require explicit config, optional extras, trusted
  plugins, generated wiring, and project-owned runtime policy.
