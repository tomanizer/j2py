# Framework Plugin Authoring

Use this guide when writing or changing a trusted framework plugin. For user-facing plugin
concepts, start with [Framework plugins](../FRAMEWORK_PLUGINS.md).

Framework plugins run during translation. They can inspect framework annotations and emit
reviewable Python fragments or metadata. j2py writes that metadata to sidecars.
`j2py-wire` uses sidecars to generate target-stack wiring.

## Plugin Or Config?

| Need | Use |
|------|-----|
| Simple annotation rename or comment | `annotation_map` |
| Project naming/import/type policy | config maps |
| Annotation logic that combines class, field, method, or parameter facts | framework plugin |
| Cross-file app assembly | `j2py-wire` target or project code |
| Real runtime policy such as database sessions, auth, transactions, or secrets | project application code |

Plugins are trusted Python code registered from a Python config file. YAML/TOML config can
set simple values, but cannot safely carry plugin objects.

## Public Contract

The plugin API lives in `j2py/framework.py`:

- `FrameworkPlugin`
- `FrameworkContext`
- `FrameworkTransformResult`
- `FrameworkAnnotation`
- `FrameworkParam`
- `InitParam`
- `FrameworkMetadataRecord`

Plugin hooks are no-op by default:

```python
class FrameworkPlugin:
    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult: ...
    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult: ...
    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult: ...
```

Return `FrameworkTransformResult(handled=True, ...)` only when the plugin claims that
element. A handled plugin suppresses later plugins and the simple `annotation_map` path
for that element.

## Minimal Plugin Shape

```python
from j2py.framework import FrameworkContext, FrameworkPlugin, FrameworkTransformResult


class ExampleControllerPlugin(FrameworkPlugin):
    name = "example-controller"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult:
        if not any(annotation.simple_name == "Controller" for annotation in ctx.annotations):
            return FrameworkTransformResult()
        return FrameworkTransformResult(
            prefix_lines=("# TODO(j2py): review generated controller adapter",),
            metadata={
                "example": {
                    "role": "controller",
                    "java_name": ctx.java_name,
                    "python_name": ctx.py_name,
                }
            },
            handled=True,
        )
```

Register it in trusted Python config:

```python
from my_migration.plugins import ExampleControllerPlugin

framework_plugins = [ExampleControllerPlugin()]
emit_wiring_metadata = True
```

## Sidecar Expectations

When `emit_wiring_metadata = True`, plugin metadata is written into generic
`*.wiring.json` sidecars. The sidecar schema is in `j2py/wire/schema.py`.

A plugin should keep metadata:

- JSON-serializable;
- versioned when it has a framework profile;
- stable enough for generated wiring tests;
- explicit about review-required runtime policy.

Do not write a separate plugin-specific sidecar format unless there is a strong design
reason and an ADR.

## Tests

Add tests that prove:

- translation succeeds with and without the plugin;
- `handled=True` suppresses fallback annotation behavior for the claimed element;
- plugin output appears in the generated Python where expected;
- sidecar metadata is emitted only when `emit_wiring_metadata = True`;
- invalid or unsupported framework shapes produce warnings or TODOs, not silent behavior.

Useful test locations:

- `tests/translate/skeleton/test_framework_plugins.py`
- `tests/translate/skeleton/test_spring_wiring_plugin.py`
- `tests/fixtures/framework/`
- `tests/wire/`

Run:

```bash
pytest tests/translate/skeleton/test_framework_plugins.py tests/translate/skeleton/test_spring_wiring_plugin.py tests/wire -q
```

For Spring-specific smoke coverage:

```bash
make test-spring-smoke
```

## Review Checklist

- The plugin is opt-in through trusted Python config.
- It does not make core j2py framework-specific.
- It emits reviewable Python and/or sidecar metadata, not hidden runtime behavior.
- Metadata uses the generic sidecar path.
- Tests cover both translated output and sidecar output.
