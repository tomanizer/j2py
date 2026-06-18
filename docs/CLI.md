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
| `--llm-provider` | `anthropic` or `gemini`; overrides config. |
| `--model`, `-m` | Provider model ID; overrides config/default. |
| `--validate` / `--no-validate` | Run Python syntax, ruff, and mypy validation when available. |
| `--dry-run` | Print translated output and do not write files. |
| `--report PATH` | Write a self-contained side-by-side HTML report. |
| `--dashboard PATH` | Write a directory dashboard from this translation run. |
| `--incremental` | Skip unchanged directory files using `.j2py-state.json`. |
| `--workers N` | Directory translation worker threads. |
| `--llm-concurrency N` | Maximum concurrent LLM calls during directory translation. |
| `--json` | Emit machine-readable translation result JSON. |

Examples:

```bash
j2py translate SomeClass.java --no-llm --dry-run
j2py translate src/main/java --output translated_py --no-llm --incremental
j2py translate src/main/java --output translated_py --dashboard dashboard.html --no-llm
```

Exit status is non-zero when validation or structural verification finds blocking issues.
Rule-layer TODOs and semantic warnings are surfaced in diagnostics, but they are not the
same as Python validation failures.

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
| `--llm-provider` | `anthropic` or `gemini`; overrides config. |
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
| `--llm-provider` | `anthropic` or `gemini`; overrides config. |
| `--model`, `-m` | Provider model ID. |
| `--validate` / `--no-validate` | Run validation on output. |
| `--poll-interval` | Polling interval in seconds. Default: `0.5`. |

The current implementation polls file hashes; install the `watch` extra for future
watch-related dependencies.

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

See [j2py doctor](DOCTOR.md) for the assessment schema and workflows.

## `j2py sarif`

Convert a doctor assessment JSON file into SARIF 2.1.0 for code-scanning workflows.

```bash
j2py sarif j2py-assessment.json --output j2py.sarif
```

See [SARIF export](SARIF.md).

## Config Discovery

Commands that translate or assess source load defaults, then auto-discover the first
project config under the source root, then apply repeated `--config` files in command-line
order. Later layers override earlier scalar values and merge mapping fields.

See [Configuration](configuration.md).
