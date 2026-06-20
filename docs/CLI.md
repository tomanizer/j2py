# CLI Reference

The `j2py` command is a Typer CLI for translating Java source, assessing migration
readiness, and generating review artifacts.

```bash
j2py --help
```

## `j2py translate`

Translate one Java file or a directory tree.

```bash
j2py translate SOURCE [--output PATH] [--config PATH] [--no-llm] [--no-validate]
```

Common options:

| Option | Meaning |
|--------|---------|
| `--output`, `-o` | Output file for a source file, or output directory for a source tree. |
| `--config`, `-c` | Extra config file. Repeat to layer multiple files after auto-discovered config. |
| `--llm` / `--no-llm` | Enable or disable LLM completion. LLM is enabled by default for this command. |
| `--llm-provider` | `anthropic`, `gemini`, or `openai`; overrides config. |
| `--llm-base-url` | Base URL for OpenAI-compatible providers; overrides config and `OPENAI_BASE_URL`. |
| `--model`, `-m` | Provider model ID; overrides config/default. |
| `--validate` / `--no-validate` | Run Python syntax, ruff, and mypy validation when available. |
| `--dry-run` | Print translated output and do not write files. |
| `--report PATH` | Write a self-contained side-by-side HTML report. |
| `--dashboard PATH` | Write a directory dashboard from this translation run. |
| `--incremental` | Skip unchanged directory files using `.j2py-state.json`. |
| `--workers N` | Directory translation worker threads. |
| `--llm-concurrency N` | Maximum concurrent LLM calls during directory translation. |
| `--llm-review` | Run an opt-in, non-mutating LLM review after translation. |
| `--llm-review-scope all\|warnings\|low-confidence` | Select which translated files receive LLM review. Default: `all`. |
| `--review-report PATH` | Write machine-readable LLM review findings as JSON. |
| `--json` | Emit machine-readable translation result JSON. |

Examples:

```bash
j2py translate SomeClass.java --no-llm --dry-run
j2py translate src/main/java --output translated_py --no-llm --incremental
j2py translate src/main/java --output translated_py --dashboard dashboard.html --no-llm
j2py translate SomeClass.java --llm-provider openai --llm-base-url https://provider.example/v1 --model provider-model-id
j2py translate src/main/java --output translated_py --no-llm --llm-review --review-report review.json
```

Exit status is non-zero when validation or structural verification finds blocking issues.
Rule-layer TODOs and semantic warnings are surfaced in diagnostics, but they are not the
same as Python validation failures.

LLM review is a second-opinion audit pass, not a repair pass. It can run even when
translation used `--no-llm`, and it can review full-confidence files. Review findings are
reported separately from rule-layer diagnostics and do not change generated Python,
coverage, or confidence score.

Review scopes:

| Scope | Reviewed files |
|-------|----------------|
| `all` | Every translated file, including full-confidence files. |
| `warnings` | Files with parse, validation, or structural issues, semantic warnings, framework metadata, or TODO markers. |
| `low-confidence` | Files below the low-confidence review threshold. |

When `--json` is used, each result includes `llm_review_ran`,
`llm_review_findings`, and `llm_review_error`. `--review-report` writes the same review
surface in a compact per-file JSON document for automation.

## `j2py analyze`

Print class inventory, parse-error status, dependency graph edges, and translation order
without translating.

```bash
j2py analyze src/main/java
j2py analyze SomeClass.java
```

Use this when you want a quick structural view of Java sources before translation.

## `j2py compare`

Open a side-by-side Java/Python diff for one source file. If the Python file already
exists, translation is skipped and the existing file is used.

```bash
j2py compare SomeClass.java [--output SomeClass.py]
```

Options:

| Option | Meaning |
|--------|---------|
| `--output`, `-o` | Python file to compare against or generate. |
| `--config`, `-c` | Extra config file. |
| `--llm` / `--no-llm` | Use LLM while generating the Python file. Default is off for speed. |
| `--llm-provider` | `anthropic`, `gemini`, or `openai`; overrides config. |
| `--llm-base-url` | Base URL for OpenAI-compatible providers; overrides config and `OPENAI_BASE_URL`. |
| `--model`, `-m` | Provider model ID. |
| `--editor` | Editor binary for the diff, for example `code`, `code-insiders`, or `cursor`. |
| `--no-open` | Print Java/Python paths and diff command without launching the editor. |
| `--validate` / `--no-validate` | Run validation during generated translation. |

Examples:

```bash
j2py compare SomeClass.java --no-llm
j2py compare SomeClass.java --editor cursor --no-llm
j2py compare SomeClass.java --no-open --no-llm
```

## `j2py watch`

Watch Java sources and re-translate changes until interrupted.

```bash
j2py watch SOURCE --output PATH
```

Options:

| Option | Meaning |
|--------|---------|
| `--output`, `-o` | Required output file or directory. |
| `--config`, `-c` | Extra config file. |
| `--llm` / `--no-llm` | Use LLM completion for unresolved logic. |
| `--llm-provider` | `anthropic`, `gemini`, or `openai`; overrides config. |
| `--llm-base-url` | Base URL for OpenAI-compatible providers; overrides config and `OPENAI_BASE_URL`. |
| `--model`, `-m` | Provider model ID. |
| `--validate` / `--no-validate` | Run validation on output. |
| `--poll-interval` | Polling interval in seconds. Default: `0.5`. |

The current implementation polls file hashes and does not require the `watch` extra.

## `j2py dashboard`

Regenerate a dashboard from an existing directory translation state file.

```bash
j2py dashboard translated_py --output dashboard.html
```

The output root must contain `.j2py-state.json`, which `j2py translate --incremental` and
directory translation writes.

## `j2py doctor`

Assess Java sources before migration without live LLM calls.

```bash
j2py doctor src/main/java
j2py doctor src/main/java --json j2py-assessment.json --html j2py-assessment.html
j2py doctor src/main/java --config-suggestions j2py.suggested.yaml
```

Options:

| Option | Meaning |
|--------|---------|
| `--config`, `-c` | Extra config file. |
| `--json PATH` | Write machine-readable assessment JSON. |
| `--html PATH` | Write a static HTML assessment report. |
| `--config-suggestions PATH` | Write advisory config suggestions YAML. |
| `--include-validation` | Run generated-Python validation during assessment. |
| `--sample-limit N` | Assess only the first N Java files in deterministic path order. |

Compare two assessment JSON files:

```bash
j2py doctor diff before.json after.json
j2py doctor diff before.json after.json --json diff.json
```

See [Assessment](DOCTOR.md) for the layer guide and [j2py doctor](DOCTOR.md) for the
assessment schema and workflows.

## `j2py sarif`

Convert a doctor assessment JSON file into SARIF 2.1.0 for code-scanning workflows.

```bash
j2py sarif j2py-assessment.json --output j2py.sarif
```

See [SARIF export](SARIF.md).

## `j2py-wire`

`j2py-wire` is the sibling CLI for post-translation framework wiring. It reads
`*.wiring.json` sidecars emitted by `j2py translate` and generates or validates target
framework glue. The current target is FastAPI.

List sidecars:

```bash
j2py-wire list translated_py
```

Generate FastAPI wiring:

```bash
j2py-wire generate translated_py \
  --target fastapi \
  --output translated_py/wiring
```

Validate generated wiring:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring
```

Validation can emit JSON for CI:

```bash
j2py-wire validate translated_py \
  --target fastapi \
  --wiring-dir translated_py/wiring \
  --format json
```

Validation exits `0` for no findings, `1` for warnings only, and `2` for errors. A
`missing-session-factory` warning is expected until the generated `get_session()` stub is
replaced or overridden by project application code.

For Spring JDBC migrations, validation still checks generated FastAPI wiring, imports,
providers, route handlers, and session placeholders. It does not convert
`jdbc_bean` sidecar metadata into a production SQLAlchemy engine/session lifecycle; that
runtime policy remains project-owned.

For the wiring layer guide, see [Wiring](WIRING.md). For the Spring-specific workflow, see
[Spring conversion](SPRING_CONVERSION.md).

## Config Discovery

Commands that translate or assess source load defaults, then auto-discover the first
project config under the source root, then apply repeated `--config` files in command-line
order. Later layers override earlier scalar values and merge mapping fields.

See [Configuration](CONFIGURATION.md).
