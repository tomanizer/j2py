# j2py doctor

`j2py doctor` is the assessment layer for Java-to-Python migration. It scans Java
sources before or during migration and produces evidence about what j2py can see, what it
can translate deterministically, and where project policy or manual work is likely
needed.

It is an evidence report, not a full Java compiler, classpath-aware migration planner, or
automatic framework migration tool. The base `doctor` command does not call live LLM
provider APIs.

## Overview / When to use

Use `doctor` when you need answers before committing to a migration path:

| Question | Assessment signal |
|---|---|
| Can j2py parse this source tree? | Parse failures and per-file parse status. |
| What Java structure is visible? | Class, method, field, import, annotation, and dependency graph inventory. |
| How much can the rule layer translate today? | Rule coverage, confidence, semantic warnings, TODOs, and unhandled diagnostics. |
| Which APIs or methods deserve attention? | Class/method ranges, method readiness, warning/TODO counts, and equivalence-test candidate flags. |
| What config should we consider? | Advisory `import_map`, `type_map`, and `annotation_map` suggestions. |
| Which framework boundaries need policy? | Annotation inventory and unresolved framework/platform imports. |
| Did a config or rule change help? | `j2py doctor diff before.json after.json`. |
| What should CI or reviewers see? | JSON, HTML, and SARIF-ready assessment artifacts. |

The important point is that assessment is evidence, not authority. It can show unresolved
imports and framework annotations, but it should not silently decide dependency
injection, persistence, transactions, servlet lifecycle, authentication, or production
runtime policy.

## What doctor does

`j2py doctor` runs deterministic local checks:

1. Parses Java files with the same parser used by translation.
2. Builds symbol and dependency graph information where available.
3. Runs rule-only translation with `use_llm=False`.
4. Collects rule coverage, confidence, diagnostics, TODOs, semantic warnings, imports,
   annotations, and class/method-level assessment signals.
5. Optionally runs generated-Python validation when `--include-validation` is set.
6. Emits JSON, HTML, config suggestions, and assessment diffs.
7. `doctor advise` can call a configured LLM to produce migration recommendations from the
   same deterministic evidence payload.

By default the base assessment command also skips Python validation checks so it can run
without optional `ruff` or `mypy` installs.

## Command reference

### Basic usage

Print the assessment JSON to stdout:

```bash
j2py doctor assess src/main/java
```

Write JSON and HTML reports:

```bash
j2py doctor assess src/main/java \
  --json j2py-assessment.json \
  --html j2py-assessment.html
```

Write advisory config suggestions:

```bash
j2py doctor assess src/main/java --config-suggestions j2py.suggested.yaml
```

Compare two assessments after changing config or rules:

```bash
j2py doctor diff before.json after.json
```

Generate migration recommendations for an assessment:

```bash
j2py doctor advise assessment.json
j2py doctor advise assessment.json \
  --provider anthropic \
  --model claude-test \
  --output-format json \
  --output j2py-doctor-advice.json
```

Assess one file:

```bash
j2py doctor assess src/main/java/com/acme/Orders.java --json orders-assessment.json
```

Use explicit j2py config:

```bash
j2py doctor assess src/main/java \
  --config j2py.yaml \
  --json j2py-assessment.json
```

Run generated-Python validation during assessment:

```bash
j2py doctor assess src/main/java \
  --include-validation \
  --json j2py-assessment.json
```

Limit a large assessment to the first N Java files in deterministic path order:

```bash
j2py doctor assess src/main/java --sample-limit 100 --html j2py-sample.html
```

### Options

| Option | Meaning |
|---|---|
| `--json PATH` | Write machine-readable assessment JSON. Without `--json`, `--html`, or `--config-suggestions`, JSON is printed to stdout. With `doctor diff`, write diff JSON. |
| `--html PATH` | Write a self-contained static HTML assessment report. |
| `--config-suggestions PATH` | Write advisory YAML containing observed config suggestion candidates. |
| `--config PATH`, `-c PATH` | Layer an explicit j2py config file on top of defaults. Repeatable. |
| `--include-validation` | Run syntax, ruff, and mypy validation on rule-only generated Python. |
| `--sample-limit N` | Assess only the first N Java files after deterministic path sorting. |

`doctor advise` options:

| Option | Meaning |
|---|---|
| `assessment` | A deterministic assessment JSON payload from `j2py doctor assess --json`. |
| `--provider`, `--llm-provider` | LLM provider override (`anthropic`, `gemini`, `openai`). |
| `--model`, `-m` | LLM model ID. |
| `--llm-base-url` | OpenAI-compatible API base URL override. |
| `--config`, `-c` | Optional extra config files used to resolve defaults. |
| `--output`, `-o` | Write output to file; defaults to stdout. |
| `--output-format markdown|json` | Return markdown directly or write JSON envelope. |
| `--max-evidence-items N` | Cap per-section evidence examples added to the model context. |
| `--cache/--no-cache` | Enable or disable cached advice responses. |

Missing source paths fail with a normal CLI error and do not write output files.

## Outputs

### JSON

Use JSON for automation and diffs:

```bash
j2py doctor assess src/main/java --json j2py-assessment.json
```

The JSON payload is deterministic and versioned with `schema_version: 2`. The top-level
keys are:

| Key | Meaning |
|---|---|
| `summary` | File, class, method, parse-failure, rule-coverage, warning, TODO, risk, legacy readiness, migration-readiness, equivalence-candidate, and unresolved-import counts. |
| `dependency_graph` | Translation order and dependency graph warnings from existing analyzer output. |
| `project_structure` | Detected Maven/Gradle build files, source roots, test roots, generated-source roots, modules, and Java language level when declared. |
| `annotation_inventory` | Observed Java annotation names and counts. |
| `unresolved_imports` | Imports not covered by defaults, user config, or project declarations. |
| `config_suggestions` | Advisory `import_map`, `type_map`, and `annotation_map` candidates. |
| `hotspots` | Ranked unhandled node types, warning reasons, import packages, annotations, risk reasons, files (coverage/risk), and high-risk methods. |
| `diagnostic_clusters` | Repeated warning and unhandled families with file counts, node-type summaries, owner hints, sample locations, and examples. |
| `recommended_next_commands` | Follow-up commands grounded in the assessed source path. |
| `files` | Per-file parse, symbol, import, annotation, and rule-only translation diagnostics. |

Each entry under `files` includes:

- `path`, `package`, `parse_ok`, and `parse_errors`;
- `classes` with field, method, and nested-class inventory, including tree-sitter source
  ranges where available;
- raw Java `imports`;
- `project_structure` with the detected module, source root, and source-set classification;
- observed `annotations`;
- per-file `unresolved_imports`;
- `migration_readiness.bucket`, `risk_score`, `risk_band`, `reasons`, and `next_action`;
- legacy mirror fields: `risk_score`, `risk_band`, `readiness_bucket`, and `risk_reasons`;
- `translation.rule_coverage` and surfaced `translation.confidence`;
- `translation.semantic_warnings`, `translation.unhandled`, `translation.todos`;
- `translation.validation` when validation was requested.

Class entries include `qualified_name`, `line`, `end_line`, `range_source`,
`diagnostics`, `migration_readiness`, and `risk_score`/`risk_band` when the parser can
derive a source range. Method entries preserve the existing `name`, `return_type`,
`line`, and `static` fields and add:

- `signature` in the same `Class.method(Type,Type)` shape used by the equivalence surface
  report;
- `end_line` and `range_source`;
- `parameters`, `constructor`, `abstract`, `public`, and `visibility`;
- `diagnostics.semantic_warnings`, `diagnostics.unhandled`, and `diagnostics.todos`;
- `migration_readiness.bucket`, `risk_score`, `risk_band`, `reasons`, and `next_action`;
- `equivalence_candidate` plus a short reason.

Method diagnostic assignment uses deterministic source-line containment:
`diagnostic_mapping_source: "source_line_containment"`. That is intentionally approximate:
the doctor does not maintain generated-Python-to-Java line mapping. Method TODO counts are
Java source comment TODO/FIXME counts inside the method range (`todo_source:
"java_source_comments"`); generated Python TODO lines remain available at file level under
`translation.todos`.

`migration_readiness.bucket` uses these deterministic values:

| Bucket | Meaning |
|---|---|
| `ready_to_translate` | No parse, rule, config, boundary, warning, TODO, or validation blockers were observed. |
| `needs_config` | Unresolved project or third-party imports need reviewed config mapping, stubs, or project-owned handling. |
| `needs_rule_work` | Rule coverage, unhandled diagnostics, or requested validation failures indicate translator work is needed before bulk migration. |
| `framework_boundary` | Framework/platform imports or annotations require explicit target-stack policy. |
| `manual_port` | Semantic warnings or TODOs require human review, but no stronger blocker was observed. |
| `parse_blocked` | Java parse errors prevent reliable migration assessment for the file. |

### HTML

Use HTML for review:

```bash
j2py doctor assess src/main/java --html j2py-assessment.html
```

The report is static and self-contained, so it can be shared as a CI artifact or review
attachment. It summarizes file count, parse failures, average rule coverage, risk,
readiness, semantic warnings, unhandled diagnostics, unresolved imports, per-file
status, project structure, annotation names, hotspots, recurring diagnostic clusters,
high-risk methods, and recommended next commands.

### Config Suggestions

Use config suggestions as a draft:

```bash
j2py doctor assess src/main/java --config-suggestions j2py.suggested.yaml
```

Suggestions are conservative. They identify candidates; they do not decide framework
semantics such as dependency injection, transactions, persistence, JDBC, servlets, or
lifecycle behavior. Review them before copying entries into `j2py.yaml`, `j2py.toml`,
`pyproject.toml`, or `j2py_config.py`.

### Diffs

Use diffs after config or rule changes:

```bash
j2py doctor diff before.json after.json
```

Good changes should reduce parse failures, unresolved imports, semantic warnings,
unhandled diagnostics, low-coverage hotspots, and migration risk without hiding real
framework policy.

### SARIF

Use SARIF for code-scanning workflows:

```bash
j2py doctor assess src/main/java --json j2py-assessment.json --include-validation
j2py sarif j2py-assessment.json --output j2py.sarif
```

See [SARIF export](SARIF.md).

## Interpreting output

Start with these report areas:

| Report area | How to use it |
|---|---|
| Summary | Check file count, parse failures, average coverage, risk/readiness bands, semantic warnings, TODOs, and unresolved imports. |
| Files | Find low-coverage or warning-heavy files before bulk translation. |
| High-Risk Methods | Find specific public APIs or method bodies that carry warnings, unhandled constructs, or TODO comments. |
| Annotation inventory | Decide which annotations are comments, drops, `annotation_map`, or framework plugins. |
| Unresolved imports | Decide which imports need `import_map`, `type_map`, stubs, plugins, or manual porting. |
| Hotspots | Identify repeated rule gaps worth fixing once instead of reviewing file-by-file. |
| Recommended commands | Use as next-step prompts, not as a migration plan. |

`rule_coverage` is the raw rule-layer node coverage. It measures handled Java syntax. It
is not proof of runtime equivalence.

`confidence` is the user-facing trust signal after parse, validation, structural, and
semantic-warning concerns are considered. A high-confidence file still needs review when
it crosses framework or runtime boundaries.

`semantic_warnings` are handled constructs that still need attention because Python and
Java behavior may differ. Integer division is a common example.

`unhandled` diagnostics are constructs the deterministic rule layer could not translate
fully. They are direct inputs for rule-layer improvements or manual review.

`unresolved_imports` are imports not covered by current defaults, user config, or project
declarations visible in the scanned source root. They are candidates for `import_map`,
`type_map`, project stubs, framework plugins, or manual porting.

## How assessment feeds the pipeline

Assessment should guide the next layer:

| Assessment finding | Likely next action |
|---|---|
| Repeated unresolved project imports | Add reviewed `import_map` or `type_map` config. |
| Repeated harmless annotations | Add reviewed `drop_annotations` or `annotation_map` entries. |
| Framework annotations with real runtime meaning | Use framework plugins or manual target-stack design. |
| Low rule coverage in common constructs | Add deterministic translator rules and fixtures. |
| Warnings in critical methods | Add behavior or equivalence tests before trusting output. |
| Sidecar-worthy framework facts | Enable trusted plugins and `emit_wiring_metadata`. |

Do not feed raw assessment JSON directly into translation as policy. Current `j2py
translate` does not consume assessment JSON directly, and that is intentional until there
is a reviewed behavior to apply.

Current direct consumers include:

- `j2py doctor assess --config-suggestions j2py.suggested.yaml`;
- `j2py doctor diff before.json after.json`;
- `j2py sarif j2py-assessment.json --output j2py.sarif`.

Planned direct consumers include:

- `j2py stubgen --from-assessment j2py-assessment.json`.

Direct `j2py translate --assessment j2py-assessment.json` support should only be added
once there is a concrete behavior to reuse, such as selecting a file subset or applying a
reviewed generated config. Raw doctor findings should not silently change translation
semantics.

## Common workflows

### First migration scan

```bash
j2py doctor assess src/main/java \
  --json j2py-assessment.json \
  --html j2py-assessment.html
```

Review the summary first, then inspect unresolved imports and annotation inventory before
adding project config.

### Check whether config helped

```bash
j2py doctor assess src/main/java --json before.json
j2py doctor assess src/main/java --config j2py.yaml --json after.json
j2py doctor diff before.json after.json
```

Use the diff output to confirm whether unresolved imports, semantic warnings, unhandled
diagnostics, parse failures, and average rule coverage improved.

### Export config suggestions

```bash
j2py doctor assess src/main/java --config-suggestions j2py.suggested.yaml
```

The suggestions file is an advisory artifact. Review it before copying entries into
`j2py.yaml`, `j2py.toml`, or another explicit config file. Suggestions are intentionally
low-confidence unless current defaults already define the behavior.

### Export SARIF

```bash
j2py doctor assess src/main/java --json j2py-assessment.json --include-validation
j2py sarif j2py-assessment.json --output j2py.sarif
```

### Validate generated Python during assessment

```bash
j2py doctor assess src/main/java --include-validation --json j2py-assessment.json
```

Use this when you want early syntax, ruff, and mypy feedback from rule-only output. It is
slower than the default scan and may skip validation tools that are not installed.

## Testing assessment quality

A good assessment workflow is repeatable:

```bash
j2py doctor assess src/main/java --json before.json --html before.html
# update reviewed config or translator rules
j2py doctor assess src/main/java --config j2py.toml --json after.json --html after.html
j2py doctor diff before.json after.json
```

If you are contributing to j2py itself, run the focused doctor tests:

```bash
uv run pytest tests/test_doctor.py -q
```

For docs and release checklist coverage:

```bash
uv run pytest tests/test_release_coverage_inventory.py tests/test_release_candidate_checklist.py -q
```

## Limits

Current `doctor` does not:

- resolve a full Java classpath;
- inspect Maven or Gradle dependency graphs deeply;
- prove runtime equivalence;
- call LLM repair;
- generate a final project config file without review;
- export SARIF directly from `translate` results;
- generate stubs;
- generate target-stack wiring;
- replace corpus scoreboards, behavior tests, equivalence tests, or `make check`.

Use assessment to choose where to spend engineering effort. Use translation, wiring,
validation, and tests to prove the migrated code.

## Roadmap and requirements

`j2py doctor` exists to answer three practical migration questions:

1. What can j2py understand today?
2. What is risky or likely to need project policy or manual work?
3. What should the developer run or configure next?

Primary users are migration developers preparing or iterating on a Java-to-Python port.
Secondary users are reviewers and technical leads who need a stable JSON/HTML report.
Tooling and CI authors can use the machine-readable schema for SARIF, dashboards, pull
request comments, or future IDE integration.

### Current status

The current implementation provides:

- `j2py doctor assess <file|dir>`;
- deterministic `schema_version: 2` JSON output;
- static HTML report output;
- source/class/method/field inventory from the existing parser/analyzer;
- Java parse-error reporting;
- dependency-graph translation order and graph warnings;
- Maven/Gradle build-system, source-root, module, generated-source, and Java language-level
  detection without invoking external build tools;
- rule-only translation coverage, confidence, semantic warnings, TODOs, and unhandled
  diagnostics;
- per-file `migration_readiness` scoring, six actionable readiness buckets, legacy
  readiness mirrors, and top-risk hotspots;
- annotation inventory;
- unresolved import candidates;
- conservative advisory config suggestions;
- advisory config suggestion export via `--config-suggestions`;
- hotspot aggregation for common unhandled nodes, warning reasons, import packages,
  annotations, risk reasons, low-coverage files, and highest-risk files;
- assessment diffs via `j2py doctor diff before.json after.json`;
- standalone SARIF export via `j2py sarif j2py-assessment.json --output j2py.sarif`;
- optional validation via `--include-validation`.

### Functional requirements

| ID | Requirement |
|---|---|
| D1 | Run without live LLM provider APIs. |
| D2 | Accept a Java file or source tree and fail missing paths with a controlled CLI error. |
| D3 | Emit a deterministic, versioned JSON assessment schema. |
| D4 | Emit a self-contained static HTML report. |
| D5 | Classify likely JDK, framework, third-party, project-internal, and annotation boundary work without deciding project policy. |
| D6 | Provide conservative config suggestions through `--config-suggestions`. |
| D7 | Support risk scoring and prioritization from observable evidence. |
| D8 | Aggregate hotspots for unhandled nodes, warnings, imports, annotations, risk reasons, warning-heavy files, low-coverage files, and highest-risk files. |
| D9 | Detect common Java project structure such as Maven, Gradle, source roots, multi-module layouts, and Java language level when available. |
| D10 | Feed the standalone SARIF exporter; future integrated command: `j2py doctor assess src/main/java --sarif j2py.sarif`. |
| D11 | Support assessment diffs. |
| D12 | Identify methods/classes that are good candidates for literal-oracle equivalence tests. |
| D13 | Produce stable reusable artifacts for config suggestions, SARIF conversion, stub generation, assessment diffs, dashboards, and review comments. |
| D14 | Report repeated warning/unhandled diagnostic clusters with owner hints and sample locations. |

### Non-goals

- Full Java compiler/classpath resolution.
- Full-library semantic equivalence proof.
- Live LLM repair or prompt execution.
- Automatic framework migration.
- Automatic generation of complete stubs for arbitrary third-party APIs.
- Silently changing translation semantics based on raw assessment findings.
- A promise that risk scoring is a complete migration plan.
- Replacing corpus scoreboards, behavior tests, equivalence tests, or `make check`.

### Success criteria

1. `j2py doctor assess <src>` runs without LLM API keys.
2. Missing source paths fail with a clean CLI error.
3. JSON output is deterministic and schema-versioned.
4. HTML output is self-contained and usable without network access.
5. Reports distinguish raw rule coverage from surfaced confidence and semantic warnings.
6. Boundary/config suggestions are conservative and reviewable.
7. A migration developer can identify the top files, packages, imports, annotations, and
   rule gaps to address next.
8. The same assessment schema can feed future SARIF, dashboard, and review tooling
   without requiring `translate` to consume raw assessment findings.

### Roadmap

| Phase | Scope |
|---|---|
| Phase 1 - Baseline assessment | JSON/HTML output, parser/analyzer inventory, rule-only translation diagnostics, annotation and unresolved import inventories, conservative config suggestions, hotspot aggregation, assessment diffs, and standalone SARIF export. |
| Phase 2 - Better prioritization | Build/source-root detection, boundary classification improvements, risk scoring, package-level summaries, and richer hotspot aggregation. |
| Phase 3 - Workflow integration | Direct `doctor --sarif` integration, translation-result SARIF export, manual-port report, and review dashboard alignment. |
| Phase 4 - Migration intelligence | Stubgen handoff, equivalence-test candidate discovery, optional Java semantic adapters such as JDT LS/OpenRewrite kept off the default path, and IDE extension support after JSON/SARIF contracts are stable. |

## Related docs

- [Configuration](CONFIGURATION.md) explains how to turn reviewed findings into project
  policy.
- [Framework plugins](FRAMEWORK_PLUGINS.md) explains how framework metadata is
  extracted.
- [Wiring](WIRING.md) explains sidecar-to-target-stack app assembly.
- [SARIF](SARIF.md) explains code-scanning export from assessment JSON.
- [Product requirements](PRODUCT_REQUIREMENTS.md) records the top-level product scope.
- [Architecture](ARCHITECTURE.md) records pipeline and component responsibilities.
- [ADR 0020](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md) records the JDK
  and platform-boundary policy.
