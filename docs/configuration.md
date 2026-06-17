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

The default `pip install j2py-converter` path keeps Anthropic support only. If a project
sets `llm_provider: gemini` without the extra installed, j2py raises an actionable error
that points at the `j2py-converter[gemini]` install command.

## YAML

```yaml
emit_type_hints: true
snake_case_methods: true
workers: 8
llm_concurrency: 4
llm_provider: gemini
model: gemini-3.5-flash

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
llm_provider = "gemini"
model = "gemini-3.5-flash"

[type_map]
MyType = "mymodule.MyType"
```

In `pyproject.toml`, use `[tool.j2py]`:

```toml
[tool.j2py]
emit_type_hints = true
snake_case_methods = true
llm_provider = "gemini"
model = "gemini-3.5-flash"

[tool.j2py.type_map]
MyType = "mymodule.MyType"

[tool.j2py.annotation_map.RestController]
python_decorator = "rest_controller"
import = "from myapp.spring_shim import rest_controller"
```

## Python

Python config is trusted-code configuration and must be passed explicitly:

```bash
uv run j2py translate src/main/java --config j2py_config.py
```

```python
type_map = {"MyType": "mymodule.MyType"}
annotation_map = {
    "RestController": {
        "python_decorator": "rest_controller",
        "import": "from myapp.spring_shim import rest_controller",
    },
}
drop_imports = {"java.io.Serializable"}
target_python = "3.12"
llm_provider = "gemini"
model = "gemini-3.5-flash"
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
- `llm_provider`: optional string, one of `anthropic` or `gemini`
- `model`: optional string model ID

`llm_provider` and `model` are project defaults for LLM-enabled translation. CLI flags
still win when present, so `--llm-provider anthropic` or `--model <id>` can override a
project config default for one command. API keys are runtime secrets and should stay in
environment variables such as `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`, not config files.
The Gemini provider also requires installing the `gemini` extra; Anthropic remains the
default provider and core dependency.

Mapping options:

- `type_map`: map Java type names to Python type expressions
- `collection_map`: map Java collection raw types to Python collection types
- `exception_map`: map Java exception names to Python exception names
- `literal_map`: map Java literal tokens to Python literal tokens
- `import_map`: map Java imports to Python import statements
- `annotation_map`: map Java annotation simple names or fully qualified names to explicit
  Python lowering behavior
- `framework_plugins`: trusted Python plugin objects for programmatic framework lowering

Each `annotation_map` entry is strict. Supported entry fields:

- `python_decorator`: emit `@<value>` above mapped classes or methods. Annotation member
  placeholders such as `{value}` and `{path}` are substituted from annotation arguments.
- `import`: add one or more Python import lines required by the mapped output.
- `python_base`: append a base class to mapped class declarations.
- `field_comment`: emit a formatted comment above the field initialization. Field
  placeholders include `{field_name}`, `{field_type}`, and `{java_type}`.
- `emit_init_param`: for instance fields, add the field to `__init__` and assign
  `self.<field> = <field>` instead of emitting a `None` default.
- `drop`: explicitly drop the annotation.
- `preserve_comment`: controls whether the original `# @Annotation(...)` audit comment is
  emitted for mapped annotations. The default follows `emit_line_comments`.

`annotation_map` is opt-in project policy. j2py does not ship a default Spring, FastAPI,
JPA, or DI mapping. Unmapped annotations keep the normal Tier 1 behavior: diagnostics plus
optional line comments.

For a worked Spring example, see the [Spring → FastAPI/SQLAlchemy mapping
cookbook](examples/SPRING_MAPPING_COOKBOOK.md) and its reference map, shipped as both
[`spring-to-fastapi.toml`](examples/spring-to-fastapi.toml) (loads via the stdlib) and
[`spring-to-fastapi.yaml`](examples/spring-to-fastapi.yaml) (needs the `[yaml]` extra).

## Framework Plugins

`framework_plugins` is the Tier 4 extension point for framework annotations whose lowering
needs programmatic logic rather than a one-to-one `annotation_map` entry. Plugins subclass
`j2py.framework.FrameworkPlugin` and may implement any of `transform_class`,
`transform_field`, or `transform_method`.

Plugins are trusted Python objects, so they can only be registered from a `.py` config file.
YAML, TOML, and `pyproject.toml` can enable `emit_wiring_metadata`, but they cannot carry
plugin instances.

```python
# j2py_config.py
from my_project.j2py_plugins import MyFrameworkPlugin

framework_plugins = [MyFrameworkPlugin()]
emit_wiring_metadata = True
```

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
Python shims.
