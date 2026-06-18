# j2py doctor

`j2py doctor` assesses Java sources before or during a migration. It is an evidence
report, not a full Java compiler or classpath-aware migration planner.

Product requirements and roadmap: [DOCTOR_PRD.md](DOCTOR_PRD.md).

## When to use it

Run `doctor` before bulk translation when you want to know:

- whether j2py can parse the source tree;
- which classes, fields, methods, imports, and annotations are visible to j2py;
- where the rule layer emits semantic warnings, TODOs, or unhandled diagnostics;
- which imports and annotations probably need project configuration or manual policy;
- what command to run next.

The command never calls the LLM layer. By default it also skips Python validation checks
so it can run without optional `ruff` or `mypy` installs.

## Basic usage

Print the assessment JSON to stdout:

```bash
j2py doctor src/main/java
```

Write JSON and HTML reports:

```bash
j2py doctor src/main/java \
  --json j2py-assessment.json \
  --html j2py-assessment.html
```

Write advisory config suggestions:

```bash
j2py doctor src/main/java --config-suggestions j2py.suggested.yaml
```

Compare two assessments after changing config or rules:

```bash
j2py doctor diff before.json after.json
```

Assess one file:

```bash
j2py doctor src/main/java/com/acme/Orders.java --json orders-assessment.json
```

Use explicit j2py config:

```bash
j2py doctor src/main/java \
  --config j2py.yaml \
  --json j2py-assessment.json
```

Run generated-Python validation during assessment:

```bash
j2py doctor src/main/java \
  --include-validation \
  --json j2py-assessment.json
```

Limit a large assessment to the first N Java files in deterministic path order:

```bash
j2py doctor src/main/java --sample-limit 100 --html j2py-sample.html
```

## Options

| Option | Meaning |
|---|---|
| `--json PATH` | Write machine-readable assessment JSON. Without `--json`, `--html`, or `--config-suggestions`, JSON is printed to stdout. With `doctor diff`, write diff JSON. |
| `--html PATH` | Write a self-contained static HTML assessment report. |
| `--config-suggestions PATH` | Write advisory YAML containing observed config suggestion candidates. |
| `--config PATH`, `-c PATH` | Layer an explicit j2py config file on top of defaults. Repeatable. |
| `--include-validation` | Run syntax, ruff, and mypy validation on rule-only generated Python. |
| `--sample-limit N` | Assess only the first N Java files after deterministic path sorting. |

Missing source paths fail with a normal CLI error and do not write output files.

## What the report contains

The report is produced from deterministic j2py stages only:

- tree-sitter Java parsing;
- symbol extraction and dependency graph analysis;
- rule-only translation with `use_llm=False`;
- optional local validation when `--include-validation` is set.

The HTML report summarizes:

- file count, parse failures, average rule coverage, semantic warnings, unhandled
  diagnostics, and unresolved imports;
- per-file package, parse status, coverage, warning count, unhandled count, and unresolved
  import count;
- observed annotation names;
- unresolved import boundary candidates;
- hotspot rankings for unhandled node types, semantic warning reasons, unresolved import
  packages, and lowest-coverage files;
- recommended next commands.

## JSON schema

The JSON payload is versioned with `schema_version: 1`. The top-level keys are:

| Key | Meaning |
|---|---|
| `summary` | File, class, parse-failure, rule-coverage, warning, TODO, and unresolved-import counts |
| `dependency_graph` | Translation order and dependency graph warnings from existing analyzer output |
| `annotation_inventory` | Observed Java annotation names and counts |
| `unresolved_imports` | Imports not covered by defaults, user config, or project declarations |
| `config_suggestions` | Advisory `import_map`, `type_map`, and `annotation_map` candidates |
| `hotspots` | Ranked unhandled node types, warning reasons, import packages, annotations, and files |
| `recommended_next_commands` | Follow-up commands grounded in the assessed source path |
| `files` | Per-file parse, symbol, import, annotation, and rule-only translation diagnostics |

Each entry under `files` includes:

- `path`, `package`, `parse_ok`, and `parse_errors`;
- `classes` with field, method, and nested-class inventory;
- raw Java `imports`;
- observed `annotations`;
- per-file `unresolved_imports`;
- `translation.rule_coverage` and surfaced `translation.confidence`;
- `translation.semantic_warnings`, `translation.unhandled`, `translation.todos`;
- `translation.validation` when validation was requested.

## Interpreting output

`rule_coverage` is the raw rule-layer node coverage. `confidence` is the user-facing trust
signal and may be lower when parse, validation, structural, or semantic-warning issues are
present. A file can have high rule coverage and still require review.

`semantic_warnings` are handled constructs that need review because Python and Java may
not have identical behavior. Integer division is a common example.

`unhandled` diagnostics are constructs the deterministic rule layer could not translate
fully. They are the most direct inputs for new rule-layer work.

`unresolved_imports` are imports not covered by current defaults, user config, or project
declarations visible in the scanned source root. They are candidates for `import_map`,
`type_map`, project stubs, framework plugins, or manual porting.

Config suggestions are intentionally conservative. They identify likely project policy
points, but they do not decide framework semantics such as dependency injection,
transactions, persistence, JDBC, servlets, or lifecycle behavior.

## Using the output with j2py

Current `doctor` output is a machine-readable assessment, but `j2py translate` does not
consume `j2py-assessment.json` directly yet. Treat the JSON as diagnostic input for
review, scripting, and follow-up tooling.

Today, the useful handoff points are:

- `config_suggestions`: copy reviewed suggestions into `j2py.yaml`, `j2py.toml`, or an
  explicit Python config;
- `unresolved_imports`: decide which imports need `import_map`, `type_map`, project
  stubs, framework plugins, or manual porting;
- `annotation_inventory`: decide which annotations should stay as comments, be dropped,
  use `annotation_map`, or use a framework plugin;
- `translation.unhandled`: choose deterministic rule-layer work or future target tests;
- `translation.semantic_warnings`: identify translated code that still needs reviewer
  attention even when rule coverage is high.

Current direct consumers include:

- `j2py doctor --config-suggestions j2py.suggested.yaml`;
- `j2py doctor diff before.json after.json`.

Planned direct consumers include:

- `j2py sarif j2py-assessment.json --output j2py.sarif`;
- `j2py stubgen --from-assessment j2py-assessment.json`.

Direct `j2py translate --assessment j2py-assessment.json` support should only be added
once there is a concrete behavior to reuse, such as selecting a file subset or applying a
reviewed generated config. Raw doctor findings should not silently change translation
semantics.

## Common workflows

### First migration scan

```bash
j2py doctor src/main/java \
  --json j2py-assessment.json \
  --html j2py-assessment.html
```

Review the summary first, then inspect unresolved imports and annotation inventory before
adding project config.

### Check whether config helped

```bash
j2py doctor src/main/java --json before.json
j2py doctor src/main/java --config j2py.yaml --json after.json
j2py doctor diff before.json after.json
```

Use the diff output to confirm whether unresolved imports, semantic warnings, unhandled
diagnostics, parse failures, and average rule coverage improved.

### Export config suggestions

```bash
j2py doctor src/main/java --config-suggestions j2py.suggested.yaml
```

The suggestions file is an advisory artifact. Review it before copying entries into
`j2py.yaml`, `j2py.toml`, or another explicit config file. Suggestions are intentionally
low-confidence unless current defaults already define the behavior.

### Validate generated Python during assessment

```bash
j2py doctor src/main/java --include-validation --json j2py-assessment.json
```

Use this when you want early syntax, ruff, and mypy feedback from rule-only output. It is
slower than the default scan and may skip validation tools that are not installed.

## Limits

Current `doctor` does not:

- resolve a full Java classpath;
- inspect Maven or Gradle dependency graphs;
- prove runtime equivalence;
- call LLM repair;
- generate a reviewed production-ready config file;
- export SARIF;
- generate stubs;
- rank files by a formal risk score.

Those are planned follow-on capabilities in [DOCTOR_PRD.md](DOCTOR_PRD.md).
