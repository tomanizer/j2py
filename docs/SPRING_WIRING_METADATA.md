# Spring Wiring Metadata Profile

This document defines the v1 Spring wiring metadata profile for optional Spring
conversion. The profile is a contract for Spring-aware framework plugins and downstream
tools such as `j2py-wire`; it is not a new sidecar format and it is not FastAPI
generation. Implementers should apply the
[Spring roadmap guardrails](SPRING_ROADMAP_GUARDRAILS.md) before changing this profile.

## Boundary

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

## Enabling Emission

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

## Module Identity

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

## Common Rules

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

## Component And Class Roles

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

## Routes

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

## Route Composition

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

## Dependency Injection

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

## Repository And Entity Hints

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

## Spring JDBC Beans

Spring JDBC configuration metadata uses method elements for `@Bean` methods that return
known JDBC infrastructure types:

- `DataSource`
- `JdbcTemplate`
- `NamedParameterJdbcTemplate`
- `PlatformTransactionManager`
- `DataSourceTransactionManager`

The method element stores bean topology under `jdbc_bean`:

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

## Fixture

The representative profile fixture lives at
`tests/fixtures/framework/spring_wiring_profile_v1.json`. The corresponding schema tests
verify that it uses the generic top-level sidecar shape, stores Spring facts only under
`elements[].metadata.spring`, covers the v1 metadata families, and preserves the route
composition boundary.
