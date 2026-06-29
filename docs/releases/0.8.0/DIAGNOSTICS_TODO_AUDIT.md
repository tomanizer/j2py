# 0.8.0 diagnostics and TODO wording audit

This audit records the release-facing diagnostics and TODO messages users are likely to
see in 0.8.0 boundary cases. The goal is honest output: generated Python should stay
reviewable, and unsupported behavior should tell users what to configure or port next.

## Boundary wording inventory

| Area | User-facing wording | Diagnostic category | Next action |
|---|---|---|---|
| Raw JDBC imports | `TODO(j2py): JDBC boundary uses placeholders; configure import_map/type_map or migrate through SQLAlchemy/project DB shim.` | `jdbc-boundary` | Configure `import_map` / `type_map`, or migrate through SQLAlchemy or a project DB facade. |
| Unsupported `JdbcTemplate` call shape | `TODO(j2py): JdbcTemplate.<method> without SQL argument` or another specific unsupported reason | `spring-jdbc-sqlalchemy-todo` | Manually port the JDBC call; do not treat the placeholder as runtime behavior. |
| Unsupported RowMapper or callback shape | `TODO(j2py): JdbcTemplate RowMapper/callback requires manual mapper port; lower to SQLAlchemy row mapping or a project DB facade` | `spring-jdbc-sqlalchemy-todo` | Port the mapper to explicit SQLAlchemy row mapping or a project-owned DB facade. |
| Spring JDBC bean metadata | `Spring JDBC bean metadata captured; wire an equivalent SQLAlchemy Engine, Connection, or Session dependency in project code` | `spring-jdbc-boundary` | Use generated sidecar metadata to wire a project-owned SQLAlchemy dependency. |
| Spring XML bean metadata | `Spring XML bean metadata captured for project-owned wiring` | Spring metadata | Use sidecar metadata to generate or hand-write project-owned wiring; do not treat XML ingestion as a Spring container. |
| Spring Data JPQL query | `TODO(j2py): manually port JPQL query to SQLAlchemy or a project repository method` | Spring Data repository stub | Translate the JPQL into SQLAlchemy or a project repository method. |
| Spring Data derived query | `TODO(j2py): manually port Spring Data derived query method <name> to SQLAlchemy or a project repository method` | Spring Data repository stub | Implement the derived-query semantics explicitly. |
| Spring `@Value` injection | `TODO(j2py): @Value injection is hard to lower statically` plus a `Replace with: ... settings.<name>` hint | annotation comments | Move the value into project settings/config wiring. |
| Static import fallback | `static import <name> emitted as qualified fallback; verify external member semantics` | static-import warning | Add static import facts/config or manually verify the external member behavior. |
| LLM skipped on parse errors | `Java parse errors detected; skipping LLM completion` | directory warning | Fix the Java parse problem before relying on rule or LLM completion. |

## Audit result

- JDBC placeholder output points to `import_map` / `type_map` or a SQLAlchemy/project DB
  shim.
- Unsupported Spring JDBC calls emit TODO text that matches the diagnostic reason
  instead of always showing the RowMapper callback message.
- RowMapper TODO wording names the concrete manual action: port to SQLAlchemy row
  mapping or a project DB facade.
- Spring JDBC bean diagnostics tell users to wire a SQLAlchemy `Engine`, `Connection`,
  or `Session` dependency in project code.
- Spring XML metadata remains metadata for project-owned wiring, not generated container
  runtime behavior.
- Spring Data JPQL and derived-query TODOs say to manually port the repository query to
  SQLAlchemy or a project repository method.

## Checks

Focused tests cover the wording contracts in:

- `tests/translate/test_platform_imports.py`
- `tests/translate/test_jdbc_sqlalchemy_calls.py`
- `tests/translate/test_jdbc_row_mapper.py`
- `tests/translate/skeleton/test_spring_wiring_plugin.py`
- `tests/translate/skeleton/test_fields_enums.py`
