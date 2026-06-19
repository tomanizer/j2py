# 0.7.0 release test coverage inventory

This inventory maps release-facing 0.7.0 claims to the checked-in evidence that backs
them. It is a maintenance aid for the release notes, README, Spring conversion guide,
and Spring mapping cookbook; it does not expand product scope.

## Claim-to-evidence map

| Release-facing claim | Primary docs | Test, fixture, or smoke evidence |
|---|---|---|
| Core Java-to-Python translation produces reviewable Python for common classes, methods, constructors, fields, records, enums, interfaces, overloads, streams, control flow, collection calls, JDK calls, and package-ordered directory translation. | `docs/GETTING_STARTED.md`, `docs/CLI.md`, `docs/ARCHITECTURE.md`, `docs/OUTPUT_REVIEW.md` | `make check`; `tests/translate/skeleton/`; `tests/translate/test_*.py`; `tests/fixtures/java/`; `tests/fixtures/python/`; `tests/equivalence/` |
| Translation output includes review artifacts: confidence, structured diagnostics, TODO markers, HTML reports, dashboards, and comparison reports. | `docs/OUTPUT_REVIEW.md`, `docs/CLI.md` | `tests/test_report.py`; `tests/cli/test_main.py`; `tests/test_pipeline.py`; `tests/fixtures/java/PartialUnsupported.java` |
| Project assessment works through `j2py doctor`, JSON and HTML reports, conservative config suggestions, diffs, and SARIF export. | `docs/DOCTOR.md`, `docs/SARIF.md`, `docs/CLI.md` | `tests/test_doctor.py`; `tests/test_sarif.py`; `tests/cli/test_main.py::test_cli_doctor_writes_json_and_html_assessment`; `tests/cli/test_main.py::test_cli_sarif_writes_report_from_doctor_assessment` |
| Optional LLM completion and review are available, while normal tests and release gates remain useful without live provider calls. | `docs/CLI.md`, `docs/OUTPUT_REVIEW.md`, `docs/LLM_HARVEST.md`, `docs/RELEASING.md` | `pyproject.toml` excludes `live_llm` from normal pytest; `make check`; `make release-check`; `tests/llm/test_client.py`; `tests/llm/test_llm_pipeline_repair.py`; `tests/llm/test_e2e_llm.py` is explicitly marked `live_llm` and run only through on-demand Make targets |
| Spring conversion scaffolding is opt-in through `annotation_map_preset: spring`, `SpringWiringPlugin`, sidecars, `j2py-wire generate`, and `j2py-wire validate`. | `docs/SPRING_CONVERSION.md`, `docs/FRAMEWORK_PLUGINS.md`, `docs/SPRING_WIRING_METADATA.md` | `tests/translate/skeleton/test_annotation_visibility.py`; `tests/translate/skeleton/test_spring_wiring_plugin.py`; `tests/test_spring_wiring_metadata_profile.py`; `tests/wire/test_cli.py`; `tests/wire/test_fastapi_target.py`; `tests/wire/test_validation.py`; `tests/integration/test_petclinic_smoke.py`; `make test-spring-smoke` |
| JPA and Spring repository scaffolding emit reviewable SQLAlchemy-oriented output for supported patterns. | `docs/examples/SPRING_MAPPING_COOKBOOK.md`, `docs/SPRING_CONVERSION.md` | `tests/translate/skeleton/test_fields_enums.py::test_spring_data_repository_lowers_to_session_backed_class`; `tests/fixtures/java/SpringDataRepository.java`; `tests/fixtures/python/SpringDataRepository.py`; `tests/fixtures/corpus/spring-app/OrderEntity.java` |
| Spring JDBC support lowers supported `JdbcTemplate` and `NamedParameterJdbcTemplate` calls to SQLAlchemy Core scaffolds. | `docs/examples/SPRING_MAPPING_COOKBOOK.md`, `docs/SPRING_WIRING_METADATA.md` | `tests/translate/test_jdbc_sqlalchemy_calls.py`; `tests/fixtures/java/JdbcTemplateSqlAlchemyScaffold.java`; `tests/fixtures/python/JdbcTemplateSqlAlchemyScaffold.py` |
| Supported RowMapper shapes lower deterministically, while unsupported callback or method-reference cases remain explicit TODOs. | `docs/examples/SPRING_MAPPING_COOKBOOK.md` | `tests/translate/test_jdbc_row_mapper.py`; `tests/fixtures/java/JdbcRowMapperScaffold.java`; `tests/fixtures/python/JdbcRowMapperScaffold.py`; `tests/translate/test_jdbc_row_mapper.py::test_unsupported_row_mapper_method_reference_remains_explicit_todo` |
| Raw JDBC, native driver bridges, framework container behavior, and production SQLAlchemy engine or session policy remain project-owned boundaries. | `docs/POSITIONING.md`, `docs/examples/SPRING_MAPPING_COOKBOOK.md`, `docs/RELEASE_NOTES_0.7.0.md` | `tests/translate/test_platform_imports.py::test_raw_jdbc_fixture_preserves_boundaries_without_java_imports`; `tests/fixtures/java/RawJdbcBoundary.java`; `tests/translate/skeleton/test_spring_wiring_plugin.py::test_jdbc_bean_methods_emit_topology_metadata_and_boundary_warning` |
| Package metadata supports core installs, optional Spring trial installs, and optional LLM-provider extras without pulling Spring runtime dependencies into the default import path. | `docs/INSTALL.md`, `docs/RELEASING.md`, `docs/RELEASE_NOTES_0.7.0.md` | `tests/packaging/test_pyproject_dependencies.py`; `make release-check`; `dist-check`; publish workflow `release-test` and `release-dist` jobs |
| Release validation exercises the normal test suite, graduated target contracts, behavior corpus, Spring smoke, version checks, import smoke, package build, sdist hygiene, and twine metadata checks. | `docs/RELEASING.md`, `docs/RELEASE_NOTES_0.7.0.md` | `make release-check`; `Makefile`; `.github/workflows/publish.yml`; `tests/test_ci_workflows.py`; `tests/packaging/test_check_sdist_hygiene.py`; `tests/packaging/test_check_release_versions.py` |

## Current unsupported-boundary checks

Unsupported release-facing boundaries are covered by explicit TODO or diagnostic checks:

- Raw `java.sql` / `javax.sql` imports do not become Java module imports; they lower to
  placeholders plus a JDBC-boundary TODO unless project `import_map` config supplies a
  concrete Python target.
- Unsupported RowMapper callback and method-reference shapes emit
  `TODO(j2py): JdbcTemplate RowMapper/callback requires manual mapper port; lower to
  SQLAlchemy row mapping or a project DB facade`.
- Spring JDBC bean topology is metadata, not a generated engine/session lifecycle.
- `j2py-wire validate` reports missing project runtime providers, such as session
  factories, as wiring findings rather than pretending to own that runtime policy.

## Release maintenance notes

When editing 0.7.0 release-facing docs:

1. Keep each headline claim tied to one of the rows above, or add a new row with focused
   test, fixture, smoke, or documented command evidence.
2. Prefer small Java fixtures over broad synthetic examples when a claim needs new
   coverage.
3. Keep live LLM provider calls out of `make check`, `make release-test`, and
   `make release-check`; live probes belong behind explicit `live_llm` targets only.
4. If a documented behavior is intentionally unsupported, test the TODO or diagnostic
   boundary instead of silently weakening the output.
