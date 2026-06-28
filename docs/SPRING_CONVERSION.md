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

## Sidecars And Wiring

A translated Python file should stay focused on the Java source it came from. For example,
`OwnerController.java` becomes `owner_controller.py`, with translated classes, methods,
fields, and imports that a reviewer can compare against the original Java.

Spring applications also contain framework facts that are not normal Java control flow:

- this class is a controller;
- this method is a `GET /owners/{ownerId}` route;
- this field is injected by Spring;
- this repository expects a SQLAlchemy session in the Python runtime;
- this generated app needs a route registration step before FastAPI can serve requests.

j2py stores those framework facts in a **sidecar** file. A sidecar is a JSON companion file
written next to the translated Python module:

```text
translated_py/
  owner_controller.py
  owner_controller.wiring.json
```

The sidecar points back to the Java source and Python output, then records structured
metadata for translated elements:

```json
{
  "schema_version": 1,
  "source": "src/main/java/example/OwnerController.java",
  "output": "translated_py/owner_controller.py",
  "elements": [
    {
      "plugin": "spring-wiring",
      "kind": "method",
      "java_name": "findOwner",
      "python_name": "find_owner",
      "metadata": {
        "spring": {
          "profile_version": 1,
          "route": {
            "http_method": "GET",
            "path": "/{owner_id}",
            "handler": "find_owner"
          }
        }
      }
    }
  ]
}
```

The sidecar is not executable code and it is not a second translated module. It is a
machine-readable review artifact for downstream tools. Keeping it separate avoids hiding
framework policy inside the source translation.

**Wiring** is the framework glue generated from sidecars. For FastAPI, wiring means code
such as:

- `APIRouter(prefix="/owners")`;
- route functions decorated with `@router.get(...)` or `@router.post(...)`;
- `Depends(...)` providers for repositories and controllers;
- an `app_wiring.py` helper that registers generated routers with a `FastAPI` app;
- placeholders where your application supplies a real database session factory.

For provider-only generation, wiring means ordinary Python factory functions such as
`get_owner_service(owner_repository)` and `get_owner_controller(owner_service)`. These
providers are framework-neutral: no FastAPI `Depends(...)`, no dependency-injector
container, and no hidden database runtime.

That split gives you two review surfaces:

1. Review `*.py` files for Java-to-Python source correspondence.
2. Review `*.wiring.json` and generated wiring for framework assembly decisions.

## Why This Improves The Python App

Plain translation can produce correctly shaped Python classes that still do not run as an
application. A controller class may exist, but FastAPI does not know which routes to
serve. A repository class may exist, but no provider supplies the SQLAlchemy session. A
translated method may have the right name, but nothing has mounted it into an app.

Sidecars and wiring close that gap without turning j2py into a Spring runtime:

- translated classes stay reviewable and close to the Java source;
- framework facts become structured data instead of comments a human must rediscover;
- `j2py-wire` can generate repeatable provider functions or FastAPI glue from those facts;
- `j2py-wire validate` can report missing providers, unresolved imports, route-handler
  mismatches, and session-factory gaps before runtime;
- project code still owns production behavior such as database engines, sessions,
  transactions, authentication, and HTTP error policy.

The result is a better translated Python application scaffold: not just isolated Python
classes, but classes plus enough generated framework glue to import, start, and smoke-test
a bounded FastAPI app.

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
  markers or review comments where supported;
- lowering `@ConfigurationProperties` classes to Pydantic settings classes;
- emitting Spring route, dependency-injection, component-role, general `@Bean`, and JDBC
  bean topology facts through the generic `*.wiring.json` sidecar path;
- generating FastAPI `APIRouter`, `Depends(...)` providers, and app registration helpers
  with `j2py-wire`.

The documented sidecar profile also reserves repository and entity hint shapes for
downstream producers. `@Transactional` and `@ConfigurationProperties` support currently
shows up in translated Python rather than generated FastAPI wiring.

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

## Generate Plain Providers

Generate provider-only wiring when tests or project code need explicit constructors
without FastAPI:

```bash
j2py-wire generate translated_py \
  --target providers \
  --output translated_py/wiring
```

This writes `translated_py/wiring/providers.py`. The generated functions are ordinary
Python factories:

```python
def get_owner_repository(session: Session) -> OwnerRepository:
    return OwnerRepository(session)


def get_owner_service(owner_repository: OwnerRepository) -> OwnerService:
    return OwnerService(owner_repository)
```

Repository providers accept a caller-supplied `Session`; they do not create engines,
manage transactions, load credentials, or choose a production session lifecycle.

## Spring JDBC Conversion

Spring JDBC conversion has two separate outputs:

1. `SpringWiringPlugin` records `@Configuration` / `@Bean` JDBC topology in
   `*.wiring.json` sidecars. General Java `@Bean` methods also emit a non-JDBC `bean`
   metadata object with visible method parameters, object creation, qualifiers, and
   lifecycle attributes.
2. The rule layer lowers supported `JdbcTemplate` and `NamedParameterJdbcTemplate`
   repository calls to SQLAlchemy Core scaffolding.

Neither output creates a database runtime. j2py does not build an engine, open a
connection, manage sessions, choose transaction boundaries, run migrations, or load
credentials. Your project supplies that policy after reviewing the translated code and
sidecars.

### JDBC bean sidecars

Given a compact configuration like:

```java
@Configuration
public class SpringJdbcConfiguration {
    private Environment env;

    @Bean
    public DataSource dataSource() {
        return DataSourceBuilder.create()
            .url(env.getProperty("app.datasource.url"))
            .username(env.getProperty("app.datasource.username"))
            .driverClassName(env.getProperty("app.datasource.driver-class-name"))
            .build();
    }

    @Bean("jdbcTemplate")
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public NamedParameterJdbcTemplate namedParameterJdbcTemplate(
            JdbcTemplate jdbcTemplate) {
        return new NamedParameterJdbcTemplate(jdbcTemplate);
    }
}
```

The sidecar stores method elements with `metadata.spring.jdbc_bean` facts such as:

```json
{
  "name": "jdbcTemplate",
  "java_name": "jdbcTemplate",
  "python_name": "jdbc_template",
  "java_type": "JdbcTemplate",
  "python_type": "JdbcTemplate",
  "source_location": {"line": 51, "column": 4, "end_line": 54, "end_column": 5},
  "dependencies": [
    {
      "name": "data_source",
      "java_name": "dataSource",
      "type": "DataSource",
      "java_type": "DataSource",
      "source": "parameter"
    }
  ],
  "constructor_args": [
    {
      "type": "JdbcTemplate",
      "arguments": [{"kind": "identifier", "value": "data_source"}]
    }
  ],
  "method_calls": [],
  "properties": []
}
```

For `DataSourceBuilder` beans, `properties` records visible datasource property keys:

```json
[
  {"target": "url", "key": "app.datasource.url"},
  {"target": "username", "key": "app.datasource.username"},
  {"target": "driver", "key": "app.datasource.driver-class-name"}
]
```

Use those facts as reviewable evidence for a downstream generator or manual port. They do
not by themselves decide whether the Python app uses `Engine`, `Connection`, `Session`,
`async_sessionmaker`, `mssql+pyodbc`, SQLite, or another project-owned database facade.

### SQLAlchemy scaffolding

For supported repository calls, translated methods reference explicit connection
placeholders:

```java
return jdbcTemplate.update(
    "update owners set first_name = ? where id = ?",
    firstName,
    id);
```

```python
return self.jdbc_template_connection.execute(
    text('update owners set first_name = :p1 where id = :p2'),
    {'p1': first_name, 'p2': id_},
).rowcount
```

Named-parameter templates keep the Java parameter map:

```java
return namedJdbcTemplate.queryForObject(
    "select name from owners where id = :id",
    params,
    String.class);
```

```python
return self.named_jdbc_template_connection.execute(
    text('select name from owners where id = :id'),
    params,
).scalar_one()
```

Supported RowMapper shapes lower to SQLAlchemy row mappings:

```java
return jdbcTemplate.query(
    "select id, first_name, last_name from owners",
    (rs, rowNum) -> new Owner(
        rs.getLong("id"),
        rs.getString("first_name"),
        rs.getString("last_name")));
```

```python
return [
    Owner(row['id'], row['first_name'], row['last_name'])
    for row in self.jdbc_template_connection.execute(
        text('select id, first_name, last_name from owners')
    ).mappings()
]
```

`queryForObject(...)` with a supported mapper uses `.mappings().one()` and applies the
mapper expression to that row. `BeanPropertyRowMapper.newInstance(Owner.class)` and
`new BeanPropertyRowMapper<>(Owner.class)` lower to `Owner(**dict(row))`.

Unsupported mapper and callback shapes stay explicit:

```java
return jdbcTemplate.queryForObject(
    "select id, first_name, last_name from owners where id = ?",
    this::mapOwner,
    id);
```

```python
return __j2py_todo__(
    'TODO(j2py): JdbcTemplate RowMapper/callback requires manual mapper port; '
    'lower to SQLAlchemy row mapping or a project DB facade'
)
```

Manual work remains for method-reference mappers, multi-statement `mapRow` bodies,
dynamic column lookup, `ResultSetExtractor`, generated keys, batch updates, stored
procedures, dialect-specific result behavior, null policy, transaction policy, and
application startup.

### Verify a JDBC slice

Use the same Spring config as the broader conversion path, then inspect both the generated
Python and sidecar:

```bash
j2py translate src/main/java \
  --config j2py_config.py \
  --output translated_py \
  --no-llm

j2py-wire list translated_py
```

For local fixture checks, these commands exercise the documented JDBC surfaces:

```bash
uv run --extra test pytest \
  tests/translate/test_jdbc_sqlalchemy_calls.py \
  tests/translate/test_jdbc_row_mapper.py \
  tests/translate/skeleton/test_spring_wiring_plugin.py -q
```

`j2py-wire validate` can still validate generated FastAPI wiring, route handlers,
providers, imports, and session-factory placeholders. It does not prove that JDBC bean
metadata has been converted into a production database runtime.

## Validate Generated Wiring

Run validation after generation:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring
```

For provider-only wiring:

```bash
j2py-wire validate translated_py \
  --target providers \
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
| `orphan-providers` | Provider sidecars exist but `providers.py` is missing. |
| `provider-function` | A provider function expected from sidecars is missing from `providers.py`. |
| `provider-dependency` | An injected dependency has no generated sidecar-backed provider. |

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

## Wiring Metadata Profile

This appendix preserves the v1 Spring wiring metadata profile for optional Spring
conversion. The profile is a contract for Spring-aware framework plugins and downstream
tools such as `j2py-wire`; it is not a new sidecar format and it is not FastAPI
generation. Design and roadmap rules live in [Spring design](SPRING_DESIGN.md).

### Boundary

Spring wiring metadata must use the existing generic framework sidecar emitted by
`emit_wiring_metadata = True`:

```json
{
  "schema_version": 1,
  "source": "src/main/java/com/example/OwnerController.java",
  "output": "translated/com/example/owner_controller.py",
  "elements": []
}
```

Spring-specific facts live only under `elements[].metadata.spring`:

```json
{
  "metadata": {
    "spring": {
      "profile_version": 1
    }
  }
}
```

Do not add Spring-specific top-level keys such as `wiring`, `python_module`,
`spring_profile`, or a second `plugin` field outside `elements[]`. Other framework
plugins must be able to share the same sidecar without key collisions.

### Enabling emission

The built-in Spring metadata producer is opt-in. Register it from a trusted Python config
and enable the existing sidecar writer:

```python
from j2py.framework_plugins.spring import SpringWiringPlugin as _SpringWiringPlugin

annotation_map_preset = "spring"
framework_plugins = [_SpringWiringPlugin()]
emit_wiring_metadata = True
```

Then run translation with that config:

```bash
j2py translate src/main/java --config j2py_config.py --output translated_py
```

The plugin emits metadata through `FrameworkTransformResult.metadata`; it does not write
sidecars directly and it does not generate FastAPI or SQLAlchemy application files.

### Module identity

The v1 profile does not store `python_module` in the sidecar. `j2py-wire` should be given
the translated output root and derive module identity from the existing `output` path:

1. make `output` relative to the translated root;
2. remove the `.py` suffix;
3. convert path separators to dots;
4. treat a trailing `.__init__` as the package module.

For example, with translated root `translated/`:

```text
translated/com/example/owner_controller.py -> com.example.owner_controller
translated/com/example/__init__.py         -> com.example
```

This keeps module identity derived from existing sidecar fields and avoids making Spring
metadata responsible for generic Python import rules.

### Common rules

Every Spring metadata object must include:

```json
{
  "spring": {
    "profile_version": 1
  }
}
```

Profile v1 values use translated Python names where the downstream tool will generate
Python code, and Java names where review or source traceability matters. Nullable fields
should be explicit `null` when the absence is meaningful, for example `qualifier` or
`request_body`.

### Component and class roles

Class-level Spring stereotypes use `role`:

```json
{
  "spring": {
    "profile_version": 1,
    "role": "controller",
    "component_name": "ownerController",
    "router_prefix": "/owners"
  }
}
```

Allowed component role values:

- `controller`
- `service`
- `repository`
- `component`
- `configuration`

`component_name` is the Spring bean name when known. `router_prefix` is present only for
controller classes with class-level mapping metadata such as `@RequestMapping`.

Entity metadata also uses `role`, with value `entity`, because it describes a class-level
Spring/JPA role rather than a component stereotype.

### Routes

Method-level route annotations emit method-local facts:

```json
{
  "spring": {
    "profile_version": 1,
    "route": {
      "http_method": "GET",
      "path": "/{owner_id}",
      "handler": "find_owner",
      "status_code": 200,
      "parameters": [
        {
          "name": "owner_id",
          "java_name": "ownerId",
          "source": "path",
          "python_type": "int",
          "required": true
        }
      ],
      "request_body": null
    }
  }
}
```

Allowed route parameter `source` values:

- `path`
- `query`
- `body`
- `unknown`

Request-body metadata uses the same name/type shape:

```json
{
  "name": "form",
  "java_name": "form",
  "python_type": "OwnerRequest",
  "required": true
}
```

### Route composition

Keep class and method route facts separate:

- class metadata emits `router_prefix` from class-level mappings;
- method metadata emits only `route.path` for the method annotation;
- `j2py-wire` composes `router_prefix + route.path`.

Example:

```java
@RestController
@RequestMapping("/owners")
class OwnerController {
    @GetMapping("/{ownerId}")
    Owner findOwner(@PathVariable int ownerId) { ... }
}
```

Expected sidecar facts:

- class element: `role = "controller"`, `router_prefix = "/owners"`
- method element: `route.http_method = "GET"`, `route.path = "/{owner_id}"`,
  `route.handler = "find_owner"`

The method element should not emit `/owners/{owner_id}`; composition belongs in
`j2py-wire`.

### Dependency injection

Constructor, field, and method injection use `inject`:

```json
{
  "spring": {
    "profile_version": 1,
    "inject": {
      "name": "owner_repository",
      "java_name": "ownerRepository",
      "type": "OwnerRepository",
      "source": "constructor",
      "required": true,
      "qualifier": null
    }
  }
}
```

Allowed injection `source` values:

- `constructor`
- `field`
- `method`

`name` is the translated Python dependency name. `type` is the translated Python type
expression when known. `qualifier` is the Spring qualifier bean name when present.

### Repository and entity hints

Repository metadata can be minimal in v1:

```json
{
  "spring": {
    "profile_version": 1,
    "role": "repository",
    "entity_type": "Owner",
    "id_type": "int"
  }
}
```

Entity metadata can also be minimal:

```json
{
  "spring": {
    "profile_version": 1,
    "role": "entity",
    "table_name": "owners"
  }
}
```

These hints are enough for `j2py-wire` to associate repository providers and database
models in the PetClinic owner-slice smoke test. Full JPA relationship modeling, JPQL, and
derived-query semantics remain out of scope for profile v1.

### Spring Bean Definitions

General Java `@Bean` methods emit method-level bean-definition metadata under `bean`.
This shape records visible source facts for downstream wiring tools; it does not
instantiate beans, run lifecycle methods, resolve profiles, or emulate the Spring
container.

```json
{
  "spring": {
    "profile_version": 1,
    "bean": {
      "name": "ownerService",
      "java_name": "ownerService",
      "python_name": "owner_service",
      "java_type": "OwnerService",
      "python_type": "OwnerService",
      "source_location": {"line": 42, "column": 4, "end_line": 44, "end_column": 5},
      "dependencies": [
        {
          "name": "owner_repository",
          "java_name": "ownerRepository",
          "type": "OwnerRepository",
          "java_type": "OwnerRepository",
          "source": "parameter"
        }
      ],
      "constructor_args": [
        {"type": "OwnerService", "arguments": [{"kind": "identifier", "value": "owner_repository"}]}
      ],
      "factory_methods": [],
      "qualifier": null,
      "primary": true,
      "lazy": null,
      "init_method": "start",
      "destroy_method": "stop",
      "unsupported": []
    }
  }
}
```

| Field | Meaning |
|---|---|
| `name` | Spring bean name. Explicit `@Bean("...")`, `@Bean(name = "...")`, or `@Bean(value = "...")` wins; otherwise the Java method name. |
| `java_name` | Source Java method name for review traceability. |
| `python_name` | Translated Python method name. |
| `java_type` | Java return type text when known. |
| `python_type` | Translated Python type text when known. |
| `source_location` | Best-effort Java source range for review tooling. |
| `dependencies` | Method-parameter dependencies (translated name, Java name, type, source). |
| `constructor_args` | Object-creation expressions visible in the bean method body. |
| `factory_methods` | Visible non-JDBC method calls that may matter to project-owned factory wiring. |
| `qualifier` | `@Qualifier` value when present. |
| `primary` | Whether `@Primary` is present. |
| `lazy` | `@Lazy` value when present; otherwise `null`. |
| `init_method` | `@Bean(initMethod = "...")` when present. |
| `destroy_method` | `@Bean(destroyMethod = "...")` when present. |
| `unsupported` | Reserved for future profile/XML cases. |

`j2py-wire validate` reports duplicate `bean.name` values as errors and unresolved
bean method-parameter dependencies as warnings when no matching bean or component
provider is visible in the loaded sidecars. These are migration-readiness signals; they
do not imply that j2py can choose a runtime container policy. Spring JDBC `@Bean`
methods additionally emit `jdbc_bean` metadata (see next section).

### Spring JDBC beans

Spring JDBC configuration metadata uses method elements for `@Bean` methods that return
known JDBC infrastructure types:

- `DataSource`
- `JdbcTemplate`
- `NamedParameterJdbcTemplate`
- `PlatformTransactionManager`
- `DataSourceTransactionManager`

The method element stores bean topology under `jdbc_bean`. The field contract is:

| Field | Meaning |
|---|---|
| `name` | Spring bean name. Explicit `@Bean("...")` wins; otherwise this is the Java method name. |
| `java_name` | Source Java method name for review traceability. |
| `python_name` | Translated Python method/bean name. |
| `java_type` | Java return type text when known. |
| `python_type` | Translated Python type text when known. |
| `source_location` | Best-effort Java source range for review tooling. |
| `dependencies` | Method-parameter dependencies, including translated name, Java name, type, and source. |
| `constructor_args` | Constructor calls returned by the bean method, preserving the target type and visible arguments. |
| `method_calls` | Builder or chained method calls visible in the bean method. |
| `properties` | Visible datasource property keys, usually from `env.getProperty(...)`. |

For a `JdbcTemplate` bean:

```json
{
  "spring": {
    "profile_version": 1,
    "jdbc_bean": {
      "name": "jdbcTemplate",
      "java_name": "jdbcTemplate",
      "python_name": "jdbc_template",
      "java_type": "JdbcTemplate",
      "python_type": "JdbcTemplate",
      "source_location": {
        "line": 42,
        "column": 4,
        "end_line": 44,
        "end_column": 5
      },
      "dependencies": [
        {
          "name": "data_source",
          "java_name": "dataSource",
          "type": "DataSource",
          "java_type": "DataSource",
          "source": "parameter"
        }
      ],
      "constructor_args": [
        {
          "type": "JdbcTemplate",
          "arguments": [{"kind": "identifier", "value": "data_source"}]
        }
      ],
      "method_calls": [],
      "properties": []
    }
  }
}
```

For a `NamedParameterJdbcTemplate` bean that depends on `JdbcTemplate`, the shape is the
same:

```json
{
  "spring": {
    "profile_version": 1,
    "jdbc_bean": {
      "name": "namedParameterJdbcTemplate",
      "java_name": "namedParameterJdbcTemplate",
      "python_name": "named_parameter_jdbc_template",
      "java_type": "NamedParameterJdbcTemplate",
      "python_type": "NamedParameterJdbcTemplate",
      "dependencies": [
        {
          "name": "jdbc_template",
          "java_name": "jdbcTemplate",
          "type": "JdbcTemplate",
          "java_type": "JdbcTemplate",
          "source": "parameter"
        }
      ],
      "constructor_args": [
        {
          "type": "NamedParameterJdbcTemplate",
          "arguments": [{"kind": "identifier", "value": "jdbc_template"}]
        }
      ],
      "method_calls": [],
      "properties": []
    }
  }
}
```

For `DataSourceBuilder`-style beans, `properties` records visible
`env.getProperty(...)` keys attached to JDBC configuration setters:

```json
[
  {"target": "url", "key": "app.datasource.url"},
  {"target": "username", "key": "app.datasource.username"},
  {"target": "driver", "key": "app.datasource.driver-class-name"}
]
```

This metadata records trustworthy bean topology only. It does not create a SQLAlchemy
engine, open a database connection, emulate JDBC, or decide driver/runtime behavior.
`j2py-wire` or project-owned migration tooling owns those runtime choices.

The translator may still lower simple `JdbcTemplate` and `NamedParameterJdbcTemplate`
repository calls to SQLAlchemy Core scaffolding when the call shape is reviewable. Those
methods intentionally reference placeholders such as `self.jdbc_template_connection` and
`self.named_jdbc_template_connection`; the wiring metadata above is the evidence a
downstream generator or manual port uses to replace those placeholders with a real
SQLAlchemy `Connection` or `Session` policy. See the
[Spring mapping cookbook](examples/SPRING_MAPPING_COOKBOOK.md#6-spring-jdbc-datasource-jdbctemplate)
for the supported `update`, `queryForObject`, `query`, RowMapper, and manual-port cases.

The profile intentionally does not include engine URLs, pool settings, credentials,
transaction propagation, SQLAlchemy session lifecycle, migrations, or exception policy.
Those are application runtime choices, not source-translation facts.

### Fixture

The representative profile fixture lives at
`tests/fixtures/framework/spring_wiring_profile_v1.json`. The corresponding schema tests
verify that it uses the generic top-level sidecar shape, stores Spring facts only under
`elements[].metadata.spring`, covers the v1 metadata families, and preserves the route
composition boundary.

## Related Docs

- [Spring design](SPRING_DESIGN.md)
- [Framework plugin guide](FRAMEWORK_PLUGINS.md)
- [Spring mapping cookbook](examples/SPRING_MAPPING_COOKBOOK.md)
- [Corpus scoreboard](CORPUS_SCOREBOARD.md)
- [ADR 0024 - Spring extension boundary](decisions/0024-spring-extension-boundary.md)
- [ADR 0025 - PetClinic smoke gate](decisions/0025-petclinic-smoke-gate.md)
