# Python API

The public Python API is intentionally small. Use it when you want to embed j2py in a
script, test harness, or migration workflow rather than shelling out to the CLI.

## Basic File Translation

```python
from pathlib import Path

from j2py.config.loader import TranslationConfig
from j2py.pipeline import translate_file

cfg = TranslationConfig.default()
result = translate_file(
    Path("src/main/java/com/acme/OrderService.java"),
    cfg=cfg,
    use_llm=False,
    validate=True,
)

print(result.python_source)
print(result.confidence)
```

`translate_file()` returns `TranslationResult`.

Important fields:

| Field | Meaning |
|-------|---------|
| `source_path` | Original Java source path. |
| `python_source` | Generated Python source text. |
| `used_llm` | Whether LLM completion was used. |
| `confidence` | User-facing confidence score after parse, rule coverage, warnings, validation, and structural verification. |
| `parse_ok` | Whether tree-sitter reported no parse errors. |
| `output_path` | Optional destination path, set by directory translation or CLI writing helpers. |
| `diagnostics` | Rule-layer coverage, warnings, imports, unhandled constructs, and framework metadata. |
| `validation` | Python syntax, ruff, and mypy validation result when validation ran. |
| `structural_verification` | Post-LLM class/method presence and order check result when applicable. |
| `llm_review_ran` | Whether the opt-in LLM review pass ran for this result. |
| `llm_review_findings` | Structured non-mutating review findings returned by the LLM review pass. |
| `llm_review_error` | Review failure message when review was requested but failed for this file. |
| `skipped` | Whether directory incremental mode reused an existing output. |

## Directory Translation

```python
from pathlib import Path

from j2py.config.loader import TranslationConfig
from j2py.pipeline import translate_directory

cfg = TranslationConfig.default()
batch = translate_directory(
    Path("src/main/java"),
    Path("translated_py"),
    cfg=cfg,
    use_llm=False,
    validate=True,
    incremental=True,
)

for result in batch.files:
    if result.output_path is not None and not result.skipped:
        result.output_path.parent.mkdir(parents=True, exist_ok=True)
        result.output_path.write_text(result.python_source)
```

`translate_directory()` returns `DirectoryTranslationResult`.

Important fields:

| Field | Meaning |
|-------|---------|
| `source_root` | Java source root. |
| `output_root` | Python output root. |
| `files` | Ordered `TranslationResult` objects. |
| `order` | Dependency-aware Java translation order. |
| `warnings` | Dependency graph and parse warnings. |
| `skipped_count` | Files reused by incremental mode. |
| `translated_count` | Files translated in this run. |

Directory translation computes package-relative output paths and tracks sibling
signatures so later files can make better local import decisions.

## Loading Config

For a one-off script, `TranslationConfig.default()` is enough. To match CLI config
layering, use `ConfigLoader`:

```python
from pathlib import Path

from j2py.config.loader import ConfigLoader

cfg = (
    ConfigLoader()
    .add_defaults()
    .add_auto_discovered(Path("src/main/java"))
    .add_file(Path("j2py.local.yaml"))
    .build()
)
```

Config files may be YAML, TOML, `pyproject.toml` with `[tool.j2py]`, or Python
`j2py_config.py`. See [Configuration](configuration.md).

## Diagnostics

`TranslationResult.diagnostics` is a `TranslationDiagnostics` object when the rule layer
ran.

Useful properties and fields:

| Member | Meaning |
|--------|---------|
| `coverage` / `rule_coverage` | Handled nodes divided by handled plus unhandled nodes. |
| `semantic_warning_count` | Handled constructs that still need reviewer attention. |
| `handled` | Handled node diagnostics. |
| `unhandled` | Unsupported or ambiguous constructs. |
| `warnings` | Semantic warnings that do not reduce raw coverage. |
| `imports` | Imports required by emitted Python constructs. |
| `framework_metadata` | Metadata emitted by configured framework plugins. |

Coverage is not the same as equivalence. A file can have high rule coverage and still
need review because of semantic warnings, validation failures, or framework/runtime
boundaries.

## Validation

When `validate=True`, j2py runs Python syntax checks plus ruff and mypy when available.
Missing validation tools are reported as skipped checks rather than import failures. The
CLI install hint is:

```bash
pip install --pre "j2py-converter[validate]"
```

## Writing Reports

The CLI is the stable path for reports and dashboards. Programmatic helpers exist in
`j2py.report`:

```python
from pathlib import Path

from j2py.report import write_dashboard_for_results, write_translation_report

write_translation_report(Path("review.html"), [result])
write_dashboard_for_results(
    Path("dashboard.html"),
    batch.files,
    source_root=batch.source_root,
    output_root=batch.output_root,
)
```

## LLM Use

Set `use_llm=True` to allow completion when the rule layer leaves gaps or full-coverage
output fails syntax/type pre-validation.

```python
result = translate_file(path, cfg=cfg, use_llm=True, llm_provider="anthropic")
```

Provider keys come from the environment (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
`OPENAI_API_KEY`). For Gemini, install the `gemini` extra. For OpenAI-compatible
endpoints, install the `openai` extra, set an explicit model, and optionally set
`cfg.llm_base_url` or `OPENAI_BASE_URL`:

```python
cfg = cfg.model_copy(update={"llm_base_url": "https://openai-compatible.example/v1"})
result = translate_file(
    path,
    cfg=cfg,
    use_llm=True,
    llm_provider="openai",
    model="provider-model-id",
)
```

Set `llm_review=True` to run the separate, non-mutating review pass after translation.
The review pass uses the same provider/model selection path as LLM completion, but it has
its own prompt and cache key and stores findings on `TranslationResult` instead of
rewriting the output.

```python
result = translate_file(
    path,
    cfg=cfg,
    use_llm=False,
    llm_review=True,
    llm_review_scope="all",
    llm_provider="anthropic",
)

for finding in result.llm_review_findings:
    print(finding.severity, finding.category, finding.message)
```

`llm_review_scope` accepts:

| Scope | Reviewed files |
|-------|----------------|
| `all` | Every translated file, including full-confidence files. |
| `warnings` | Files with parse, validation, or structural issues, semantic warnings, framework metadata, or TODO markers. |
| `low-confidence` | Files below the low-confidence review threshold. |

Review failures are captured in `llm_review_error` and do not corrupt
`python_source`, coverage, or confidence.

## Stability Notes

The dataclasses in `j2py.pipeline` are the current public result shape. Lower-level
translator modules under `j2py.translate` are implementation details; prefer the pipeline
API or CLI unless you are contributing new rule-layer behavior.
