# j2py configuration

j2py loads layered configuration from defaults plus either explicitly passed files
(`--config`) or the first conventional project config found near the source root:

1. `j2py.yaml`
2. `j2py.yml`
3. `j2py.toml`
4. `pyproject.toml` under `[tool.j2py]`
5. `j2py_config.py`

Python config files remain supported for backwards compatibility. YAML config requires
the optional `yaml` extra:

```bash
pip install "j2py-converter[yaml]"
```

## YAML

```yaml
emit_type_hints: true
snake_case_methods: true
workers: 8
llm_concurrency: 4

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

[type_map]
MyType = "mymodule.MyType"
```

In `pyproject.toml`, use `[tool.j2py]`:

```toml
[tool.j2py]
emit_type_hints = true
snake_case_methods = true

[tool.j2py.type_map]
MyType = "mymodule.MyType"
```

## Python

```python
type_map = {"MyType": "mymodule.MyType"}
drop_imports = {"java.io.Serializable"}
target_python = "3.12"
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
