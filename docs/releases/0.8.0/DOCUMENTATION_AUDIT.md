# 0.8.0 release docs audit

This page records the release-facing documentation audit for 0.8.0. It is a checkpoint,
not a new product contract: the authoritative behavior remains the live CLI, config
schema, checked-in fixtures, generated output, and release gates.

## Scope

The audit covered:

- `README.md`
- `docs/INSTALL.md`
- `docs/GETTING_STARTED.md`
- `docs/CLI.md`
- `docs/CONFIGURATION.md`
- `docs/WIRING.md`
- `docs/SPRING_CONVERSION.md`
- `docs/examples/SPRING_MAPPING_COOKBOOK.md`
- `docs/FRAMEWORK_PLUGINS.md`
- `docs/SPRING_CONVERSION.md#wiring-metadata-profile`
- `docs/POSITIONING.md`
- `docs/PRODUCT_REQUIREMENTS.md`
- `docs/CASE_STUDY_JSEMVER.md`
- `docs/CASE_STUDY_COMMONS_CODEC_HEX.md`

## Verified command surface

The documented CLI surface is checked by the release gate and focused docs tests:

```bash
j2py --help
j2py translate --help
j2py analyze --help
j2py compare --help
j2py watch --help
j2py dashboard --help
j2py doctor --help
j2py sarif --help
j2py-wire --help
j2py-wire list --help
j2py-wire ingest --help
j2py-wire generate --help
j2py-wire validate --help
```

The checked `j2py-wire` contract is:

- commands: `list`, `ingest`, `generate`, and `validate`;
- target generators include FastAPI wiring plus additional provider/settings and
  persistence scaffolding targets;
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

Representative fixture output is exercised by release tests and the clean-install Spring
smoke path:

```bash
j2py translate tests/fixtures/java/JdbcTemplateSqlAlchemyScaffold.java \
  --output /private/tmp/j2py-doc-audit/jdbc_template_sqlalchemy.py \
  --no-llm --no-validate

j2py translate tests/fixtures/java/JdbcRowMapperScaffold.java \
  --output /private/tmp/j2py-doc-audit/jdbc_row_mapper.py \
  --no-llm --no-validate

j2py translate tests/fixtures/java/SpringJdbcConfiguration.java \
  --config tests/fixtures/framework/spring_wiring_plugin_config.py \
  --output /private/tmp/j2py-doc-audit/spring_jdbc_configuration.py \
  --no-llm --no-validate

j2py translate tests/fixtures/java/SpringWiringController.java \
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
- Spring XML bean definitions are captured as metadata for project-owned wiring rather
  than executed as a container model.

The generated sidecars are exercised through `j2py-wire`:

```bash
j2py-wire list /private/tmp/j2py-doc-audit
j2py-wire generate /private/tmp/j2py-doc-audit \
  --target fastapi \
  --output /private/tmp/j2py-doc-audit/wiring
j2py-wire validate /private/tmp/j2py-doc-audit \
  --target fastapi \
  --wiring-dir /private/tmp/j2py-doc-audit/wiring \
  --format json
```

The expected validation result for this focused fixture path is warnings-only:
`missing-session-factory`. That is the expected project-owned runtime boundary, not a
translation failure.

## Consistency checklist

- `docs/SPRING_CONVERSION.md` is the Spring entry point for users.
- `docs/WIRING.md` is the user-facing `j2py-wire` command and target overview.
- `docs/developer/WIRING_TARGETS.md` owns target generator implementation guidance.
- `docs/examples/SPRING_MAPPING_COOKBOOK.md` remains the lower-level support matrix and
  example catalog.
- README, the Spring guide, the cookbook, the framework plugin guide, and the Spring
  wiring metadata profile all describe the same opt-in Spring path.
- Case studies describe bounded external validation, not full-library automatic
  migration.
- No release-facing doc should describe all RowMapper cases as unsupported. The
  supported position is partial deterministic RowMapper lowering with explicit TODOs for
  callback and application-policy cases.
- No release-facing doc should imply default Spring, FastAPI, SQLAlchemy, JPA, JDBC,
  XML container, or persistence runtime behavior. Those paths require explicit config,
  optional extras, trusted plugins, generated wiring, and project-owned runtime policy.
