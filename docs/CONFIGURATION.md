# j2py configuration

Configuration is the project-policy layer in the j2py pipeline. It answers questions the
translator cannot safely guess from Java syntax alone:

- Which Java imports should become project Python imports?
- Which Java types should become Python types?
- Which annotations should be dropped, preserved, or translated into project-owned Python
  shims?
- Which LLM provider/model should this repository use by default?
- Should trusted framework plugins write metadata sidecars for `j2py-wire`?

If you remember one rule, make it this: configuration should make migration choices
explicit and reviewable. It should not hide framework behavior or production runtime
policy inside generated code.

For the full pipeline, see
[Positioning and enterprise scope](POSITIONING.md#one-pipeline-five-layers).

## What configuration owns

Use configuration for decisions that are stable project policy:

| Need | Use |
|---|---|
| Java type should become a specific Python type | `type_map`, `collection_map` |
| Java import should become a specific Python import | `import_map` |
| Java exception or literal should map to a Python equivalent | `exception_map`, `literal_map` |
| Annotation should become a Python decorator, base, comment, parameter marker, or dropped annotation | `annotation_map`, `annotation_map_preset` |
| Known static members need explicit Python binding facts | `member_map` |
| Normal translation should default to a provider/model/concurrency setting | `llm_provider`, `llm_base_url`, `model`, `llm_concurrency` |
| A trusted framework plugin should extract framework metadata | `framework_plugins` in `j2py_config.py` |
| Plugin metadata should be written for `j2py-wire` | `emit_wiring_metadata` |

Do not put runtime secrets or production application policy in j2py config. API keys belong
in environment variables. Database URLs, credentials, pool settings, transaction policy,
authentication, deployment configuration, and secrets belong in project application code or
target-stack settings, not in the source-translation config.

## How j2py uses configuration

Configuration is read before translation or assessment starts. The effective config changes
how j2py emits Python:

1. `j2py doctor` can suggest config entries for unresolved imports, framework annotations,
   and repeated project-specific patterns.
2. You review those suggestions and commit only the choices that are true project policy.
3. `j2py translate` loads the config and applies it while translating source files.
4. If configured framework plugins emit metadata, j2py writes that metadata to sidecars.
5. `j2py-wire` uses sidecars to generate target-stack wiring.

For example, this config:

```toml
[type_map]
Money = "acme.money.Money"

[import_map]
com.acme.money.Money = "from acme.money import Money"
```

means generated Python can use your real `Money` type and import instead of guessing or
leaving an unresolved Java package boundary.

## Which config format to use

| Format | Best for | Notes |
|---|---|---|
| `j2py.toml` | Most repository-owned config | Uses the Python standard library; good default choice. |
| `pyproject.toml` `[tool.j2py]` | Projects that keep tool config in `pyproject.toml` | Same schema as `j2py.toml`, nested under `[tool.j2py]`. |
| `j2py.yaml` / `j2py.yml` | Larger mapping tables that are easier to read as YAML | Requires the optional `yaml` extra. |
| `j2py_config.py` | Trusted Python objects, especially `framework_plugins` | Must be passed explicitly with `--config`; executing it runs Python code. |

Use `j2py doctor <source> --config-suggestions j2py.suggested.yaml` to draft config
candidates, then review them before committing them. Generated suggestions are advisory;
they should not be treated as trusted application policy without review.

## Discovery and layering

j2py loads configuration in layers:

1. built-in defaults;
2. the first conventional non-executable project config found under the source root;
3. repeated `--config` files, applied in command-line order.

Later scalar values override earlier scalar values. Mapping fields merge, with later keys
overriding earlier keys. Set/list fields merge as sets where applicable.

Auto-discovered project config files are checked in this order:

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

## Configuration, plugins, and wiring

Declarative config maps one visible source fact to one target policy. When the source
framework needs code to combine annotations, fields, methods, or class-level context, use a
trusted `framework_plugins` entry from `j2py_config.py`.

Framework plugins extract framework metadata. j2py writes that metadata to sidecars.
`j2py-wire` uses sidecars to generate target-stack wiring. Set
`emit_wiring_metadata = true` only when the configured plugins emit sidecar metadata that
you intend to inspect or feed to `j2py-wire`.

For plugin authoring and plugin API details, use [Framework plugins](FRAMEWORK_PLUGINS.md).
This configuration guide only explains how plugins are registered.

## How to write a useful config

Start small. A good config usually grows from actual diagnostics and review findings, not
from trying to model the whole Java ecosystem upfront.

1. Run `doctor` on a representative package:

   ```bash
   j2py doctor src/main/java \
     --config-suggestions j2py.suggested.yaml \
     --html j2py-assessment.html
   ```

2. Review the suggestions. Keep entries that reflect stable project policy. Delete guesses
   and one-off cases.
3. Put the reviewed entries in `j2py.toml`, `pyproject.toml`, or `j2py.yaml`.
4. Translate a small package with `--no-llm`:

   ```bash
   j2py translate src/main/java/com/acme/orders \
     --output translated_py \
     --config j2py.toml \
     --no-llm
   ```

5. Review output with `j2py compare`, run validation, and update config only for repeated
   project patterns.

Use these examples as patterns.

### Map project types and imports

Use `type_map` and `import_map` when Java refers to project types that already have Python
equivalents.

```toml
[type_map]
Money = "Money"
CustomerId = "CustomerId"

[import_map]
com.acme.money.Money = "from acme.money import Money"
com.acme.customer.CustomerId = "from acme.customer import CustomerId"
```

This is useful when generated methods should keep precise type hints:

```python
def total(self) -> Money:
    ...
```

### Drop noise annotations and imports

Use `drop_annotations` and `drop_imports` for Java artifacts that have no Python meaning
and would distract reviewers.

```toml
drop_annotations = ["Override", "SuppressWarnings"]
drop_imports = ["java.io.Serializable"]
```

Only drop annotations when their behavior is genuinely irrelevant. If an annotation carries
business behavior, preserve it as a comment, map it, or handle it with a plugin.

### Preserve framework intent with annotation maps

Use `annotation_map` for simple one-to-one translations. For example, a project can keep
Spring controller markers visible without claiming that j2py implements Spring:

```toml
annotation_map_preset = "spring"

[annotation_map.RestController]
python_decorator = "rest_controller"
import = "from myapp.spring_shims import rest_controller"

[annotation_map.Autowired]
field_comment = "# injected dependency: {field_type} {field_name}"
emit_init_param = true
```

This can turn a field-injected Java dependency into an explicit constructor parameter in
the generated Python. That helps reviewers see the dependency graph.

### Set LLM defaults without storing secrets

Use config for provider defaults, not API keys:

```toml
llm_provider = "openai"
llm_base_url = "https://openai-compatible.example/v1"
model = "provider-model-id"
llm_concurrency = 4
```

Put `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY` in the environment. Do not
commit secrets to config files.

### Register framework plugins only from trusted Python config

YAML and TOML can describe data. They cannot carry live Python plugin objects. Use
`j2py_config.py` only when you need a trusted plugin:

```python
from j2py.framework_plugins.spring import SpringWiringPlugin as _SpringWiringPlugin

annotation_map_preset = "spring"
framework_plugins = [_SpringWiringPlugin()]
emit_wiring_metadata = True
```

Framework plugins extract framework metadata. j2py writes that metadata to sidecars.
`j2py-wire` uses sidecars to generate target-stack wiring. Read
[Framework plugins](FRAMEWORK_PLUGINS.md) before writing your own plugin.

## How to test a config

Treat config as source-controlled migration policy. Test it before applying it broadly.

Use this loop:

```bash
j2py doctor src/main/java \
  --config j2py.toml \
  --html j2py-assessment.html

j2py translate src/main/java/com/acme/orders \
  --output /tmp/j2py-orders \
  --config j2py.toml \
  --no-llm

j2py compare src/main/java/com/acme/orders/OrderService.java \
  /tmp/j2py-orders/com/acme/orders/OrderService.py
```

A good config should:

- reduce unresolved imports or repeated annotation warnings;
- make generated imports and type hints point at real project Python modules;
- keep framework decisions visible as decorators, comments, constructor parameters, or
  sidecar metadata;
- avoid broad entries that accidentally rewrite unrelated Java constructs;
- keep generated Python reviewable against the Java source.

Red flags:

- config entries copied directly from `doctor` without review;
- `annotation_map` entries that pretend to implement framework behavior your project has
  not actually provided;
- secrets, database URLs, or production environment policy in j2py config;
- a `j2py_config.py` file that imports untrusted plugin code;
- broad type/import mappings that make translated output less auditable.

## File examples

### YAML

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

### TOML

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

### Python

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
  Python translation behavior
- `member_map`: map fully qualified Java members to explicit member-binding facts
- `framework_plugins`: trusted Python plugin objects for framework metadata extraction or
  source transforms

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
`j2py_runtime`; enable it explicitly with `annotation_map_preset: spring`. The Spring
extension scope and boundary are documented in
[SPRING_EXTENSION_PRD.md](SPRING_EXTENSION_PRD.md) and
[ADR 0024](decisions/0024-spring-extension-boundary.md); implementation guardrails live in
[SPRING_ROADMAP_GUARDRAILS.md](SPRING_ROADMAP_GUARDRAILS.md). Project `annotation_map`
entries are merged after the preset, so they can override or extend the preset. Unmapped
annotations keep normal behavior: diagnostics plus optional line comments.

Each `member_map` key is a fully qualified Java member, such as
`com.example.Util.max` or `com.example.Factory.of`. Supported entry fields:

- `kind`: `method`, `field`, or `unknown`; defaults to `unknown`.
- `python_owner`: Python owner/class name to emit for qualified fallbacks.
- `python_member`: Python method or field name to emit.
- `source`: free-form source label for diagnostics; defaults to `config`.
- `return_type`: Java return type to feed local type inference.
- `return_shape`: compact Java type-shape signature, for example `object:Thing->Thing`.
- `intrinsic`: optional intrinsic name for future plugin or built-in generated behavior.

`member_map` feeds the shared member-binding layer used by explicit static imports,
wildcard static imports when the owner/member fact is configured, qualified static calls,
and return-type inference. It is intentionally opt-in: j2py core does not ship default
Spring, JPA, servlet, or other framework member semantics. Put project/framework facts in
config or a trusted plugin instead of hardcoding them in core.

For simple worked Spring mappings, see the [Spring -> FastAPI/SQLAlchemy mapping
cookbook](examples/SPRING_MAPPING_COOKBOOK.md) and its reference map, shipped as both
[`spring-to-fastapi.toml`](examples/spring-to-fastapi.toml) (loads via the stdlib) and
[`spring-to-fastapi.yaml`](examples/spring-to-fastapi.yaml) (needs the `[yaml]` extra).
Install `j2py-converter[spring]` or run `uv sync --extra spring` only when the generated
Spring path needs FastAPI, HTTPX, SQLAlchemy, or pydantic-settings available at runtime.
For the full Spring conversion flow, including `SpringWiringPlugin`, sidecars,
`j2py-wire`, and the PetClinic smoke gate, see
[Spring conversion](SPRING_CONVERSION.md).

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
code that combines multiple source facts or emits wiring metadata.
