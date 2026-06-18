# j2py configuration

j2py loads layered configuration from defaults plus either explicitly passed files
(`--config`) or the first non-executable conventional project config found near the
source root:

1. `j2py.yaml`
2. `j2py.yml`
3. `j2py.toml`
4. `pyproject.toml` under `[tool.j2py]`

Python config files are not auto-discovered. They remain supported for backwards
compatibility only when passed explicitly with `--config`; loading one imports and
executes that Python file, so use this only for trusted configuration.

YAML config requires the optional `yaml` extra:

```bash
pip install "j2py-converter[yaml]"
```

Gemini provider configuration requires the optional `gemini` extra at install time:

```bash
pip install "j2py-converter[gemini]"
```

OpenAI-compatible provider configuration requires the optional `openai` extra at install
time:

```bash
pip install "j2py-converter[openai]"
```

The default `pip install j2py-converter` path keeps Anthropic support only. If a project
sets `llm_provider: gemini` or `llm_provider: openai` without the matching extra installed,
j2py raises an actionable error that points at the install command. `openai-compatible`
is accepted as an alias for `openai`.

## YAML

```yaml
emit_type_hints: true
snake_case_methods: true
workers: 8
llm_concurrency: 4
llm_provider: openai
llm_base_url: https://openai-compatible.example/v1
model: provider-model-id

type_map:
  MyCustomType: my_module.MyCustomType
  LegacyBean: dict

import_map:
  com.example.MyClass: "from mypackage import MyClass"

drop_imports:
  - java.util.logging
  - java.io.Serializable

drop_annotations:
  - Override
  - SuppressWarnings

annotation_map_preset: spring
annotation_map:
  RestController:
    python_decorator: rest_controller
    import: "from myapp.spring_shim import rest_controller"
  GetMapping:
    python_decorator: 'router.get("{value}")'
    import: "from myapp.web import router"
  Autowired:
    field_comment: "# injected: {field_type} {field_name}"
    emit_init_param: true
  Entity:
    python_base: Base
    import: "from myapp.db import Base"
```

## TOML

Standalone `j2py.toml` may put keys at the top level:

```toml
emit_type_hints = true
snake_case_methods = true
workers = 8
llm_provider = "openai"
llm_base_url = "https://openai-compatible.example/v1"
model = "provider-model-id"

[type_map]
MyType = "mymodule.MyType"
```

In `pyproject.toml`, use `[tool.j2py]`:

```toml
[tool.j2py]
emit_type_hints = true
snake_case_methods = true
llm_provider = "openai"
llm_base_url = "https://openai-compatible.example/v1"
model = "provider-model-id"
annotation_map_preset = "spring"

[tool.j2py.type_map]
MyType = "mymodule.MyType"

[tool.j2py.annotation_map.RestController]
python_decorator = "rest_controller"
import = "from myapp.spring_shim import rest_controller"

[tool.j2py.member_map."com.example.Factory.of"]
kind = "method"
python_owner = "Factory"
python_member = "of"
return_shape = "object:Thing->Thing"
```

## Python

Python config is trusted-code configuration and must be passed explicitly:

```bash
uv run j2py translate src/main/java --config j2py_config.py
```

```python
type_map = {"MyType": "mymodule.MyType"}
annotation_map_preset = "spring"
annotation_map = {
    "RestController": {
        "python_decorator": "rest_controller",
        "import": "from myapp.spring_shim import rest_controller",
    },
}
drop_imports = {"java.io.Serializable"}
target_python = "3.12"
llm_provider = "openai"
llm_base_url = "https://openai-compatible.example/v1"
model = "provider-model-id"
```

## Schema

Scalar options:

- `emit_type_hints`: bool
- `snake_case_methods`: bool
- `snake_case_fields`: bool
- `emit_line_comments`: bool
- `emit_docstrings`: bool
- `confidence_comments`: bool
- `emit_wiring_metadata`: bool
- `target_python`: string
- `workers`: int
- `llm_concurrency`: int
- `llm_provider`: optional string, one of `anthropic`, `gemini`, or `openai`
- `llm_base_url`: optional string for OpenAI-compatible provider endpoints
- `model`: optional string model ID

`llm_provider` and `model` are project defaults for LLM-enabled translation. CLI flags
still win when present, so `--llm-provider anthropic` or `--model <id>` can override a
project config default for one command. `llm_base_url` can be set in config, overridden
with `--llm-base-url`, or supplied through `OPENAI_BASE_URL` for OpenAI-compatible
providers.

API keys are runtime secrets and should stay in environment variables such as
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `OPENAI_API_KEY`, not config files. Gemini and
OpenAI-compatible providers also require installing their matching extras; Anthropic
remains the default provider and core dependency. OpenAI-compatible providers require an
explicit `model` because endpoint model IDs are deployment-specific.

LLM review is a runtime operation rather than a project config default. Use
`j2py translate --llm-review` / `--llm-review-scope`, or the Python API
`translate_file(..., llm_review=True, llm_review_scope="...")`, when a run needs the
non-mutating review pass. The review pass uses the same provider/model/base-url
configuration described above.

Mapping options:

- `type_map`: map Java type names to Python type expressions
- `collection_map`: map Java collection raw types to Python collection types
- `exception_map`: map Java exception names to Python exception names
- `literal_map`: map Java literal tokens to Python literal tokens
- `import_map`: map Java imports to Python import statements
- `annotation_map_preset`: optional named annotation map preset; currently `spring`
- `annotation_map`: map Java annotation simple names or fully qualified names to explicit
  Python lowering behavior
- `member_map`: map fully qualified Java members to explicit member-binding facts
- `framework_plugins`: trusted Python plugin objects for programmatic framework lowering

Each `annotation_map` entry is strict. Supported entry fields:

- `python_decorator`: emit `@<value>` above mapped classes or methods. Annotation member
  placeholders such as `{value}` and `{path}` are substituted from annotation arguments.
- `import`: add one or more Python import lines required by the mapped output.
- `python_base`: append a base class to mapped class declarations.
- `python_annotation`: wrap mapped method parameters as
  `typing.Annotated[<type>, <value>]`.
- `field_comment`: emit a formatted comment above the field initialization. Field
  placeholders include `{field_name}`, `{field_type}`, and `{java_type}`.
- `emit_init_param`: for instance fields, add the field to `__init__` and assign
  `self.<field> = <field>` instead of emitting a `None` default.
- `drop`: explicitly drop the annotation.
- `preserve_comment`: controls whether the original `# @Annotation(...)` audit comment is
  emitted for mapped annotations. The default follows `emit_line_comments`.

`annotation_map` is opt-in project policy. j2py does not enable Spring, FastAPI, JPA, or
DI mappings by default. The named `spring` preset is a convenience map of Spring
annotations to no-op marker decorators and `typing.Annotated` parameter markers from
`j2py_runtime`; enable it explicitly with `annotation_map_preset: spring`. Project
`annotation_map` entries are merged after the preset, so they can override or extend the
preset. Unmapped annotations keep the normal Tier 1 behavior: diagnostics plus optional
line comments.

Each `member_map` key is a fully qualified Java member, such as
`com.example.Util.max` or `com.example.Factory.of`. Supported entry fields:

- `kind`: `method`, `field`, or `unknown`; defaults to `unknown`.
- `python_owner`: Python owner/class name to emit for qualified fallbacks.
- `python_member`: Python method or field name to emit.
- `source`: free-form source label for diagnostics; defaults to `config`.
- `return_type`: Java return type to feed local type inference.
- `return_shape`: compact Java type-shape signature, for example `object:Thing->Thing`.
- `intrinsic`: optional intrinsic name for future plugin/built-in lowering.

`member_map` feeds the shared member-binding layer used by explicit static imports,
wildcard static imports when the owner/member fact is configured, qualified static calls,
and return-type inference. It is intentionally opt-in: j2py core does not ship default
Spring, JPA, servlet, or other framework member semantics. Put project/framework facts in
config or a trusted plugin instead of hardcoding them in core.

For simple worked Spring mappings, see the [Spring -> FastAPI/SQLAlchemy mapping
cookbook](examples/SPRING_MAPPING_COOKBOOK.md) and its reference map, shipped as both
[`spring-to-fastapi.toml`](examples/spring-to-fastapi.toml) (loads via the stdlib) and
[`spring-to-fastapi.yaml`](examples/spring-to-fastapi.yaml) (needs the `[yaml]` extra).

## Framework Plugins

`framework_plugins` is the Tier 4 extension point for framework annotations whose lowering
needs programmatic logic rather than a one-to-one `annotation_map` entry. Plugins subclass
`j2py.framework.FrameworkPlugin` and may implement any of `transform_class`,
`transform_field`, or `transform_method`. See the dedicated
[framework plugin guide](FRAMEWORK_PLUGINS.md) for the contract, quick start, and an
end-to-end Spring migration example.

Plugins are trusted Python objects, so they can only be registered from a `.py` config file.
YAML, TOML, and `pyproject.toml` can enable `emit_wiring_metadata`, but they cannot carry
plugin instances.

```python
# j2py_config.py
from my_project.j2py_plugins import MyFrameworkPlugin as _MyFrameworkPlugin

framework_plugins = [_MyFrameworkPlugin()]
emit_wiring_metadata = True
```

Plugin modules must be importable when the config file executes. For project-local plugin
packages, install the package into the active environment or set `PYTHONPATH` appropriately
when invoking `j2py`. Imported plugin classes should use a private alias, as above, because
the Python config loader exports every public top-level name as a config key.

Resolution is per element: plugins run in registration order, and the first plugin returning
`handled=True` wins for that class, field, or method. A handled plugin suppresses later
plugins and the Tier 2 `annotation_map` for that element. A plugin returning
`handled=False`, returning an invalid result, or raising an exception falls through to
`annotation_map` and then Tier 1 annotation comments with a diagnostic warning.

When `emit_wiring_metadata = True`, file and directory translation write a sidecar next to
translated Python files only when handled plugin results include non-empty JSON-serializable
metadata:

```text
orders.py
orders.wiring.json
```

The sidecar is versioned and records source/output paths, plugin name, element kind,
Java/Python names, annotations, and plugin metadata. If a later translation no longer has
metadata for the file, j2py removes the stale sidecar. j2py core does not consume this file
or generate framework bootstrap code; it is intended for downstream tooling such as the
planned `j2py-wire` follow-up.

Set/list options:

- `drop_imports`
- `drop_annotations`
- `strip_modifiers`

Unknown keys are rejected with suggestions. For example, `type_maps` raises:

```text
Unknown config key: 'type_maps'. Did you mean 'type_map'?
```

See [docs/examples/spring-to-fastapi.yaml](examples/spring-to-fastapi.yaml) for a
reference profile showing how a project might map common Spring annotations to its own
Python shims. Use [FRAMEWORK_PLUGINS.md](FRAMEWORK_PLUGINS.md) when those mappings need
programmatic logic or wiring metadata.
