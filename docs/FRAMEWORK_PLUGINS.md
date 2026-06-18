# Framework plugin architecture

Framework plugins are j2py's trusted extension point for project-specific framework
lowering. They let a migration team translate Java source structure with the normal rule
layer while adding explicit, reviewable policy for framework annotations such as Spring
MVC routes, dependency injection, transactions, and persistence markers.

Design decision: [ADR 0022](decisions/0022-framework-plugin-architecture.md).
Configuration reference: [configuration.md](configuration.md#framework-plugins).
Related Tier 2 mapping: [ADR 0019](decisions/0019-annotation-map-framework-lowering.md).
Spring extension boundary: [SPRING_EXTENSION_PRD.md](SPRING_EXTENSION_PRD.md) and
[ADR 0024](decisions/0024-spring-extension-boundary.md).
Spring roadmap guardrails: [SPRING_ROADMAP_GUARDRAILS.md](SPRING_ROADMAP_GUARDRAILS.md).
Spring wiring profile: [SPRING_WIRING_METADATA.md](SPRING_WIRING_METADATA.md).

## What plugins are for

j2py core is a Java-to-Python source translator. It is not a Spring, Hibernate, Jakarta,
JDBC, or FastAPI runtime emulator. That boundary is intentional: enterprise framework
behavior is usually application policy, not Java language semantics.

Framework plugins exist for the middle ground:

- The Java construct is already visible to j2py as syntax, usually an annotation.
- A flat `annotation_map` entry is too small because the rule needs programmatic logic.
- The migration team wants the generated Python to carry target-stack scaffolding,
  review comments, or wiring metadata without forking j2py core.

Typical plugin-owned decisions include:

- mapping a controller annotation to a project-owned FastAPI router decorator;
- promoting selected injected fields into constructor parameters;
- recording route, dependency-injection, or ORM hints in `*.wiring.json`;
- adding project shim imports and base classes;
- suppressing duplicate Tier 2 annotation output when a plugin has handled an element.

Plugins do not change the core mission. The translated Python should still be auditable
against the Java class-by-class and method-by-method. A plugin should make framework
policy more explicit, not hide it.

## Why plugins are needed

Tier 2 `annotation_map` is intentionally declarative and one-to-one. It works well for
simple rules such as:

```yaml
annotation_map:
  RestController:
    python_decorator: rest_controller
    import: "from myapp.spring_shim import rest_controller"
  Autowired:
    field_comment: "# injected: {field_type} {field_name}"
    emit_init_param: true
```

That is not enough for many enterprise framework patterns:

| Pattern | Why a plugin helps |
|---------|--------------------|
| `@RequestMapping` on a class plus `@GetMapping` on methods | Compose class-level and method-level route metadata for downstream wiring. |
| `@Autowired` fields mixed with constructor injection | Apply project-specific constructor rules and dependency metadata consistently. |
| `@Entity`, `@Table`, `@Id`, `@Column` | Record an ORM graph for a project-owned SQLAlchemy/Pydantic generation step. |
| `@Configuration` plus `@Bean` methods | Correlate members across one class instead of treating each annotation in isolation. |
| Controller -> Service -> Repository wiring | Emit per-file metadata that another tool can merge across the translated project. |

Hard-coding those rules into `j2py/translate/` would make j2py opinionated about one
target stack. Plugins keep that policy in a Python config file or an organization-owned
package where it can be reviewed, versioned, and tested with the migrated codebase.

## How this improves enterprise migration

In a framework-heavy Java codebase, the most useful split is:

1. j2py translates the Java language structure and preserves review correspondence.
2. `type_map`, `import_map`, and `annotation_map` handle simple project policy.
3. Framework plugins handle annotation lowering that needs code.
4. Optional wiring metadata feeds project-owned tools that assemble routers, dependency
   containers, ORM declarations, or migration reports.
5. Engineers review and finish framework behavior in the target stack.

This makes the migration more controlled than either a blind code rewrite or a pile of
manual notes:

- every plugin rule is source-controlled Python code;
- plugin output is visible in the generated Python;
- handled annotations are recorded in diagnostics and coverage accounting;
- plugin metadata can be emitted as JSON for audit and follow-up automation;
- core j2py remains framework-neutral.

## Quick start

Create a trusted Python config. Python configs execute code, so j2py only loads them when
you pass `--config` explicitly.

```python
# j2py_config.py
from my_migration.spring_plugin import SpringMigrationPlugin as _SpringMigrationPlugin

framework_plugins = [_SpringMigrationPlugin()]
emit_wiring_metadata = True
```

Run translation with that config:

```bash
uv run j2py translate src/main/java --output translated_py \
  --config j2py_config.py --no-llm
```

The plugin module must be importable through normal Python imports. For a project-local
plugin package, either install that package into the active environment or run with a
suitable `PYTHONPATH`, for example `PYTHONPATH=. uv run j2py ...` from the project root.
Imported helper names should start with `_`: the Python config loader treats every public
top-level name as a config key, so `SpringMigrationPlugin` would be rejected as an unknown
configuration option if imported without the private alias above.

If the plugin returns metadata and `emit_wiring_metadata = True`, j2py writes a sidecar
next to each translated Python file that has metadata:

```text
translated_py/orders.py
translated_py/orders.wiring.json
```

YAML, TOML, and `pyproject.toml` can set `emit_wiring_metadata`, but they cannot register
plugin objects. Register plugins only in trusted Python config.

## Plugin contract

Plugins subclass `j2py.framework.FrameworkPlugin` and override only the hooks they need.
The base class provides no-op defaults, so a class-only plugin does not need field or
method hooks.

```python
from j2py.framework import (
    FrameworkContext,
    FrameworkPlugin,
    FrameworkTransformResult,
    InitParam,
)


class MyFrameworkPlugin(FrameworkPlugin):
    name = "my-framework"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()

    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        return FrameworkTransformResult()
```

Each hook receives a `FrameworkContext`:

| Field | Meaning |
|-------|---------|
| `node` | The Java AST node for the class, field, method, or constructor. |
| `element_kind` | `"class"`, `"field"`, `"method"`, or `"constructor"`. |
| `java_name` / `py_name` | Original Java name and translated Python name. |
| `annotations` | Parsed annotations with full name, simple name, and string values. |
| `java_type` / `py_type` | Field type or method return type when available. |
| `parameters` | Method or constructor parameters with Java and Python names/types. |
| `diagnostics` | The translation diagnostic sink. Prefer normal return values first. |

Hooks return `FrameworkTransformResult`:

| Field | Meaning |
|-------|---------|
| `prefix_lines` | Lines to emit above the target class, field assignment, or method. |
| `base_classes` | Extra Python base classes for handled classes. |
| `init_params` | Constructor parameters promoted from handled fields. |
| `imports` | Import lines required by plugin output. |
| `metadata` | JSON-serializable hints for optional wiring sidecars. |
| `handled` | `True` when the plugin claims this element. |

`prefix_lines`, `base_classes`, and `imports` must be tuples of strings, not a bare
string. `metadata` must be JSON-serializable if you want it included in a sidecar.

## Resolution and fallback

Resolution is per class, field, method, or constructor:

1. Framework plugins run in registration order.
2. The first plugin returning `handled=True` wins for that element.
3. A handled plugin suppresses later plugins and Tier 2 `annotation_map` for that element.
4. If no plugin handles the element, Tier 2 `annotation_map` runs.
5. If neither handles it, Tier 1 annotation visibility emits diagnostics and optional
   `# @Annotation(...)` comments.

Plugin hooks are guarded. If a hook raises, returns the wrong result type, or returns raw
strings where tuple fields are required, j2py records a diagnostic warning and falls back
to the next tier. A broken plugin should not crash a translation run, but plugins are
still trusted in-process Python code and can run arbitrary side effects when imported or
called.

## Wiring metadata

Plugin metadata is collected on handled elements and can be emitted as `*.wiring.json`.
The payload is intentionally generic:

```json
{
  "schema_version": 1,
  "source": "src/main/java/com/acme/OrdersController.java",
  "output": "translated_py/com/acme/orders_controller.py",
  "elements": [
    {
      "plugin": "spring-migration",
      "kind": "method",
      "java_name": "listOrders",
      "python_name": "list_orders",
      "annotations": [
        {
          "name": "GetMapping",
          "simple_name": "GetMapping",
          "values": {"value": "/orders"}
        }
      ],
      "metadata": {
        "route": {
          "method": "GET",
          "path": "/orders",
          "handler": "list_orders"
        }
      }
    }
  ]
}
```

j2py core writes this file only when `emit_wiring_metadata = True` and at least one plugin
returns non-empty metadata. Core does not consume the sidecar or generate FastAPI app
startup code. That belongs in downstream migration tooling such as a project-owned wiring
generator.

Spring-specific route, dependency-injection, repository, and entity facts must be nested
under `elements[].metadata.spring` using the v1
[Spring wiring metadata profile](SPRING_WIRING_METADATA.md). `annotation_map_preset:
spring` remains Tier 2 marker lowering; the Spring wiring profile is structured Tier 4
plugin metadata for `j2py-wire`.

Use the built-in producer when you want Spring v1 sidecars:

```python
from j2py.framework_plugins.spring import SpringWiringPlugin as _SpringWiringPlugin

annotation_map_preset = "spring"
framework_plugins = [_SpringWiringPlugin()]
emit_wiring_metadata = True
```

## End-to-end example: Spring -> FastAPI, Pydantic, SQLAlchemy

This example is illustrative. It shows how a project can use a plugin to make Spring
application-layer intent explicit while keeping runnable target-stack assembly outside
j2py core.

Source Java:

```java
@RestController
@RequestMapping("/orders")
public class OrdersController {
    @Autowired
    private OrderService service;

    @GetMapping("/{id}")
    public OrderDto getOrder(String id) {
        return service.getOrder(id);
    }
}
```

Plugin:

```python
from __future__ import annotations

from j2py.framework import (
    FrameworkContext,
    FrameworkPlugin,
    FrameworkTransformResult,
    InitParam,
)


class SpringMigrationPlugin(FrameworkPlugin):
    name = "spring-migration"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has(ctx, "RestController"):
            return FrameworkTransformResult()
        prefix = _value(ctx, "RequestMapping", default="")
        return FrameworkTransformResult(
            prefix_lines=("@controller",),
            imports=("from myapp.web_shims import controller",),
            metadata={
                "spring": {
                    "profile_version": 1,
                    "role": "controller",
                    "component_name": ctx.py_name[:1].lower() + ctx.py_name[1:],
                    "router_prefix": prefix,
                },
            },
            handled=True,
        )

    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not _has(ctx, "Autowired"):
            return FrameworkTransformResult()
        return FrameworkTransformResult(
            prefix_lines=(f"        # injected dependency: {ctx.py_type} {ctx.py_name}",),
            init_params=(InitParam(ctx.py_name, ctx.py_type or "object"),),
            metadata={
                "spring": {
                    "profile_version": 1,
                    "inject": {
                        "name": ctx.py_name,
                        "java_name": ctx.java_name,
                        "type": ctx.py_type or "object",
                        "source": "field",
                        "required": True,
                        "qualifier": None,
                    },
                },
            },
            handled=True,
        )

    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        route = _route(ctx)
        if route is None:
            return FrameworkTransformResult()
        method, path = route
        return FrameworkTransformResult(
            prefix_lines=(f'    @route("{method}", "{path}")',),
            imports=("from myapp.web_shims import route",),
            metadata={
                "spring": {
                    "profile_version": 1,
                    "route": {
                        "http_method": method,
                        "path": path,
                        "handler": ctx.py_name,
                        "status_code": 200,
                        "parameters": [
                            {
                                "name": param.py_name,
                                "java_name": param.java_name,
                                "source": "unknown",
                                "python_type": param.py_type,
                                "required": True,
                            }
                            for param in ctx.parameters
                        ],
                        "request_body": None,
                    },
                },
            },
            handled=True,
        )


def _has(ctx: FrameworkContext, simple_name: str) -> bool:
    return any(annotation.simple_name == simple_name for annotation in ctx.annotations)


def _value(ctx: FrameworkContext, simple_name: str, *, default: str = "") -> str:
    for annotation in ctx.annotations:
        if annotation.simple_name == simple_name:
            return annotation.values.get("value", default)
    return default


def _route(ctx: FrameworkContext) -> tuple[str, str] | None:
    for simple_name, method in {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "DeleteMapping": "DELETE",
    }.items():
        if _has(ctx, simple_name):
            return method, _value(ctx, simple_name, default="")
    return None
```

Translated Python shape from this example:

```python
from __future__ import annotations

from myapp.web_shims import controller
from myapp.web_shims import route


@controller
class OrdersController:
    def __init__(self, service: OrderService) -> None:
        # injected dependency: OrderService service
        self.service: OrderService = service

    @route("GET", "/{id}")
    def get_order(self, id_: str) -> OrderDto:
        return self.service.get_order(id_)
```

The plugin has not created a complete FastAPI application. Instead, it has created a
reviewable translation plus enough explicit metadata for a downstream tool or manual port
to build the target framework layer:

- FastAPI: combine class `router_prefix` metadata with method `route` metadata to register
  `APIRouter` paths, strip or adapt `self`, and wire dependencies through `Depends`.
- Pydantic: map DTO classes with `type_map`/`import_map` and, when useful, plugin metadata
  that marks request and response models.
- SQLAlchemy: use entity/field annotations to emit metadata for table names, primary
  keys, columns, and relationships; generate or hand-finish declarative models in a
  project-owned step.
- Spring JDBC: discover `@Configuration` / `@Bean` topology for `DataSource`,
  `JdbcTemplate`, `NamedParameterJdbcTemplate`, and transaction managers, then emit
  sidecar metadata for a project-owned SQLAlchemy engine/session layer. The rule layer can
  lower simple `JdbcTemplate` calls and RowMapper expressions to SQLAlchemy Core
  scaffolding, but the plugin/runtime layer still owns real connection/session wiring.
  Keep pyodbc as a possible SQLAlchemy dialect/driver, not as a core j2py codegen target.

For simple Spring annotations that are truly one-to-one, prefer
[`annotation_map`](configuration.md#schema). Use a plugin when the rule
needs code, correlation, metadata, or project-specific precedence.

## Suggested migration workflow

1. Start with no framework plugin and translate a small, representative Java package.
2. Review Tier 1 annotation comments and diagnostics to identify repeated framework
   patterns.
3. Add `annotation_map` entries for simple one-to-one mappings.
4. Add a plugin for patterns that need code or metadata.
5. Turn on `emit_wiring_metadata` and inspect sidecars for routes, dependencies, and ORM
   hints.
6. Build target-stack wiring in project code or a separate generator, not in j2py core.
7. Add fixture tests around the plugin package so framework policy changes are reviewed
   like application code.

## Guardrails

- Keep plugins narrow. A plugin should claim only elements it understands.
- Return `handled=False` when in doubt so Tier 2 or Tier 1 remains visible.
- Prefer project-owned shim functions and decorators over pretending core j2py owns the
  target framework.
- Keep metadata JSON-serializable and version your downstream schema if another tool
  consumes it.
- Do not use plugins to hide manual-port requirements. Emit comments or metadata that make
  the remaining work easier to audit.
- Do not register untrusted plugins. They run in-process through trusted Python config.

## Relationship to existing docs

- [POSITIONING.md](POSITIONING.md) explains why framework runtime behavior remains outside
  core j2py.
- [configuration.md](configuration.md) documents config loading, `annotation_map`, and
  `framework_plugins`.
- [Spring mapping cookbook](examples/SPRING_MAPPING_COOKBOOK.md) shows Tier 2
  `annotation_map` recipes and manual-port callouts.
- [SPRING_EXTENSION_PRD.md](SPRING_EXTENSION_PRD.md) and
  [ADR 0024](decisions/0024-spring-extension-boundary.md) define the optional Spring
  extension scope and the rule that Spring is one consumer of these generic hooks.
- [SPRING_ROADMAP_GUARDRAILS.md](SPRING_ROADMAP_GUARDRAILS.md) lists the implementation
  checklist for future Spring roadmap PRs.
- [ADR 0022](decisions/0022-framework-plugin-architecture.md) records the architecture
  tradeoffs behind the plugin contract.
