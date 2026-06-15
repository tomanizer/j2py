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
```

## Python

Python config is trusted-code configuration and must be passed explicitly:

```bash
uv run j2py translate src/main/java --config j2py_config.py
```

```python
type_map = {"MyType": "mymodule.MyType"}
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
- `target_python`: string
- `workers`: int
- `llm_concurrency`: int
- `llm_provider`: optional string, one of `anthropic` or `gemini`
- `model`: optional string model ID

`llm_provider` and `model` are project defaults for LLM-enabled translation. CLI flags
still win when present, so `--llm-provider anthropic` or `--model <id>` can override a
project config default for one command. API keys are runtime secrets and should stay in
environment variables such as `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`, not config files.

Mapping options:

- `type_map`: map Java type names to Python type expressions
- `collection_map`: map Java collection raw types to Python collection types
- `exception_map`: map Java exception names to Python exception names
- `literal_map`: map Java literal tokens to Python literal tokens
- `import_map`: map Java imports to Python import statements

Set/list options:

- `drop_imports`
- `drop_annotations`
- `strip_modifiers`

Unknown keys are rejected with suggestions. For example, `type_maps` raises:

```text
Unknown config key: 'type_maps'. Did you mean 'type_map'?
```
