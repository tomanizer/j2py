# Change Routing

Classify first. Then edit only the owning surface.

## Java Construct Rule

Read:

- [Rule authoring](../developer/RULE_AUTHORING.md)
- [Translation internals](../developer/TRANSLATION_INTERNALS.md)
- [Translation targets](../TRANSLATION_TARGETS.md)

Edit:

- `j2py/translate/class_*` for class constructs
- `j2py/translate/statements.py`, `j2py/translate/stmt_*` for statements
- `j2py/translate/expressions.py`, `j2py/translate/expr_*` for expressions
- `j2py/translate/stream_*`, `j2py/translate/expr_streams.py` for streams
- `j2py/translate/rules/` for pure helpers
- `j2py/translate/runtime/j2py_runtime.py` for emitted runtime helpers
- `tests/fixtures/java/`, `tests/fixtures/python/`

Validate:

```bash
pytest tests/translate -q
make check
```

Add `make test-equivalence` or corpus checks when semantics or corpus-facing output change.

## Parser Or Analyzer Change

Read:

- [Parser and analyzer internals](../developer/PARSER_ANALYZER.md)
- [Architecture](../ARCHITECTURE.md)

Edit:

- `j2py/parse/`
- `j2py/analyze/`
- `tests/parse/`
- `tests/analyze/`

Validate:

```bash
pytest tests/parse tests/analyze -q
```

Add `make check` and corpus checks if generated output can change.

## Equivalence Or Behavior Coverage

Read:

- [Equivalence testing](../EQUIVALENCE_TESTING.md)
- [Behavior corpus](../BEHAVIOR_CORPUS.md)

Edit:

- `tests/equivalence/`
- `tests/fixtures/equivalence/`
- `tests/behavior/`
- `tests/fixtures/behavior/`

Validate:

```bash
make test-equivalence
make equivalence-report
make test-behavior
```

`make test-behavior` requires a JDK.

## Framework Plugin Change

Read:

- [Framework plugin authoring](../developer/FRAMEWORK_PLUGIN_AUTHORING.md)
- [Framework plugins](../FRAMEWORK_PLUGINS.md)
- [Java Enterprise Framework Guides](../README.md#java-enterprise-framework-guides)

Edit:

- `j2py/framework.py`
- `j2py/translate/framework_dispatch.py`
- `j2py/framework_plugins/`
- `tests/translate/skeleton/test_framework_plugins.py`
- `tests/translate/skeleton/test_spring_wiring_plugin.py`
- `tests/wire/` when sidecar consumers change

Validate:

```bash
pytest tests/translate/skeleton/test_framework_plugins.py tests/translate/skeleton/test_spring_wiring_plugin.py tests/wire -q
```

Use `make test-spring-smoke` when the Spring/FastAPI smoke path changes.

## Wiring Target Change

Read:

- [Wiring targets](../developer/WIRING_TARGETS.md)
- [Wiring](../WIRING.md)
- [CLI](../CLI.md#j2py-wire)

Edit:

- `j2py/wire/cli.py`
- `j2py/wire/loader.py`
- `j2py/wire/schema.py`
- `j2py/wire/validation.py`
- `j2py/wire/targets/`
- `tests/wire/`

Validate:

```bash
pytest tests/wire -q
```

Runtime policy remains project-owned: sessions, credentials, auth, transactions, deployment.

## Diagnostics Doctor Or SARIF Change

Read:

- [Diagnostics](../developer/DIAGNOSTICS.md)
- [Assessment](../DOCTOR.md)
- [Doctor](../DOCTOR.md)
- [SARIF](../SARIF.md)

Edit:

- `j2py/translate/diagnostics.py`
- `j2py/pipeline.py`
- `j2py/validate/`
- `j2py/doctor*.py`
- `j2py/sarif.py`
- relevant tests

Validate:

```bash
pytest tests/test_pipeline.py tests/validate tests/test_doctor.py tests/test_sarif.py -q
```

If release-facing diagnostic text changes:

```bash
pytest tests/test_release_diagnostics_todo_audit.py -q
```

## LLM Provider Or Prompt Change

Read:

- [LLM providers](../developer/LLM_PROVIDERS.md)
- [LLM harvest](../LLM_HARVEST.md)
- [Configuration](../CONFIGURATION.md)

Edit:

- `j2py/llm/client.py`
- `j2py/llm/prompts.py`
- `j2py/llm/review.py`
- `j2py/llm/harvest.py`
- `j2py/pipeline.py`
- CLI/config docs when public behavior changes

Validate:

```bash
pytest tests/llm tests/cli/test_main.py -q
```

Do not run live provider tests unless explicitly requested and credentials are available.

## CLI Or Public API Change

Read:

- [API stability](../developer/API_STABILITY.md)
- [CLI](../CLI.md)
- [API reference](../API_REFERENCE.md)

Edit:

- `j2py/cli/`
- `j2py/pipeline.py`
- public facade modules such as `j2py/doctor.py`
- `docs/API_REFERENCE.md`
- `tests/cli/test_main.py`
- `tests/test_pipeline.py`

Validate:

```bash
pytest tests/cli/test_main.py tests/test_pipeline.py -q
```

Public result models and JSON shape changes require docs updates.

## Documentation Change

Read:

- [Documentation index](../README.md)
- [Docs map](DOCS_MAP.md)
- owning user/developer/repo section

Edit:

- owning doc
- `docs/README.md` when discoverability changes
- root entry points only when they change how users, contributors, or agents start

Validate:

```bash
pytest tests/test_release_coverage_inventory.py tests/test_release_candidate_checklist.py tests/test_release_diagnostics_todo_audit.py tests/test_release_performance_baseline.py tests/packaging/test_check_sdist_hygiene.py -q
```

Also run:

```bash
pytest tests/test_docs_links.py -q
```

## Root Entrypoint Change

Read:

- [Documentation index](../README.md)
- [Contributing](../../CONTRIBUTING.md)
- [Docs map](DOCS_MAP.md#root-entrypoints)

Edit:

- `README.md` for public overview and quick start
- `CONTRIBUTING.md` for contributor workflow
- `AGENTS.md` and `CLAUDE.md` for mirrored agent instructions
- `CHANGELOG.md` for user-visible version history
- `SECURITY.md` for security policy only

Validate:

```bash
cmp -s AGENTS.md CLAUDE.md
```

Also run:

```bash
pytest tests/test_docs_links.py -q
```

## Packaging Or Release Workflow Change

Read:

- [Releasing](../RELEASING.md)
- [Validation matrix](VALIDATION_MATRIX.md)
- [Repo Hygiene And Project Record](../README.md#repo-hygiene-and-project-record)

Edit:

- `pyproject.toml`
- `uv.lock`
- `Makefile`
- `scripts/packaging/`
- `tests/packaging/`
- release docs when evidence or instructions change

Validate:

```bash
pytest tests/packaging -q
make release-check
```

Do not claim release readiness without `make release-check` or an explicit note that it
was not run.
