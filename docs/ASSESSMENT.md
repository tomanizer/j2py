# j2py assessment

Assessment is the readiness and risk-diagnosis layer in the j2py pipeline. See
[the pipeline overview](POSITIONING.md#one-pipeline-five-layers) for how assessment fits
with configuration, translation, sidecars, wiring, and review.

The main command is `j2py doctor`. It scans Java source before or during migration and
produces evidence about what j2py can see, what it can translate deterministically, and
where project policy or manual work is likely needed.

Assessment does not migrate the code for you. It helps you decide what to configure,
translate, test, or defer.

## What assessment is for

Use assessment when you need answers before committing to a migration path:

| Question | Assessment signal |
|---|---|
| Can j2py parse this source tree? | Parse failures and per-file parse status. |
| What Java structure is visible? | Class, method, field, import, annotation, and dependency graph inventory. |
| How much can the rule layer translate today? | Rule coverage, confidence, semantic warnings, TODOs, and unhandled diagnostics. |
| What config should we consider? | Advisory `import_map`, `type_map`, and `annotation_map` suggestions. |
| Which framework boundaries need policy? | Annotation inventory and unresolved framework/platform imports. |
| Did a config or rule change help? | `j2py doctor diff before.json after.json`. |
| What should CI or reviewers see? | JSON, HTML, and SARIF-ready assessment artifacts. |

The important point is that assessment is evidence, not authority. It can show unresolved
imports and framework annotations, but it should not silently decide dependency injection,
persistence, transactions, servlet lifecycle, authentication, or production runtime policy.

## What doctor does

`j2py doctor` runs deterministic local checks:

1. Parses Java files with the same parser used by translation.
2. Builds symbol and dependency graph information where available.
3. Runs rule-only translation with `use_llm=False`.
4. Collects rule coverage, confidence, diagnostics, TODOs, semantic warnings, imports, and
   annotations.
5. Optionally runs generated-Python validation when `--include-validation` is set.
6. Emits JSON, HTML, config suggestions, and assessment diffs.

It never calls live LLM provider APIs. That makes it suitable for early scans, CI checks,
and migration planning without API keys.

## Basic workflow

Run a first assessment:

```bash
j2py doctor src/main/java \
  --json j2py-assessment.json \
  --html j2py-assessment.html
```

Review the HTML first. It is the human triage view. Keep the JSON for automation,
diffs, SARIF export, and future review tooling.

Generate advisory config suggestions:

```bash
j2py doctor src/main/java \
  --config-suggestions j2py.suggested.yaml
```

Review the suggestions before copying them into `j2py.toml`, `pyproject.toml`,
`j2py.yaml`, or `j2py_config.py`.

After writing config, assess again:

```bash
j2py doctor src/main/java --json before.json
j2py doctor src/main/java --config j2py.toml --json after.json
j2py doctor diff before.json after.json
```

Then translate a narrow slice:

```bash
j2py translate src/main/java/com/acme/orders \
  --config j2py.toml \
  --output translated_py \
  --no-llm
```

## How to read the report

Start with these fields:

| Report area | How to use it |
|---|---|
| Summary | Check file count, parse failures, average coverage, semantic warnings, TODOs, and unresolved imports. |
| Files | Find low-coverage or warning-heavy files before bulk translation. |
| Annotation inventory | Decide which annotations are comments, drops, `annotation_map`, or framework plugins. |
| Unresolved imports | Decide which imports need `import_map`, `type_map`, stubs, plugins, or manual porting. |
| Hotspots | Identify repeated rule gaps worth fixing once instead of reviewing file-by-file. |
| Recommended commands | Use as next-step prompts, not as a migration plan. |

`rule_coverage` means the deterministic translator recognized Java syntax. It is not proof
of runtime equivalence.

`confidence` is the user-facing trust signal after parse, validation, structural, and
semantic-warning concerns are considered. A high-confidence file still needs review when it
crosses framework or runtime boundaries.

`semantic_warnings` are handled constructs that still need attention because Python and
Java behavior may differ.

`unhandled` diagnostics are direct inputs for rule-layer improvements or manual review.

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

## Outputs

### JSON

Use JSON for automation and diffs:

```bash
j2py doctor src/main/java --json j2py-assessment.json
```

The schema is versioned and includes summary counts, dependency graph data, annotation
inventory, unresolved imports, config suggestions, hotspots, recommended commands, and
per-file translation diagnostics.

### HTML

Use HTML for review:

```bash
j2py doctor src/main/java --html j2py-assessment.html
```

The report is static and self-contained, so it can be shared as a CI artifact or review
attachment.

### Config Suggestions

Use config suggestions as a draft:

```bash
j2py doctor src/main/java --config-suggestions j2py.suggested.yaml
```

Suggestions are conservative. They identify candidates; they do not decide framework
semantics.

### Diffs

Use diffs after config or rule changes:

```bash
j2py doctor diff before.json after.json
```

Good changes should reduce parse failures, unresolved imports, semantic warnings,
unhandled diagnostics, or low-coverage hotspots without hiding real framework policy.

### SARIF

Use SARIF for code-scanning workflows:

```bash
j2py doctor src/main/java --json j2py-assessment.json --include-validation
j2py sarif j2py-assessment.json --output j2py.sarif
```

## Testing assessment quality

A good assessment workflow is repeatable:

```bash
j2py doctor src/main/java --json before.json --html before.html
# update reviewed config or translator rules
j2py doctor src/main/java --config j2py.toml --json after.json --html after.html
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

Assessment does not currently:

- resolve a full Java classpath;
- inspect Maven or Gradle dependency graphs deeply;
- prove runtime equivalence;
- call LLM repair;
- generate a final project config without review;
- generate target-stack wiring;
- replace corpus scoreboards, behavior tests, equivalence tests, or `make check`.

Use assessment to choose where to spend engineering effort. Use translation, wiring,
validation, and tests to prove the migrated code.

## Related docs

- [Doctor](DOCTOR.md) is the command reference and schema detail.
- [Configuration](CONFIGURATION.md) explains how to turn reviewed findings into project
  policy.
- [Framework plugins](FRAMEWORK_PLUGINS.md) explains how framework metadata is extracted.
- [Wiring](WIRING.md) explains sidecar-to-target-stack app assembly.
- [SARIF](SARIF.md) explains code-scanning export from assessment JSON.
