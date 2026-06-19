# Docs Map

Use this to update the owning doc. Do not duplicate content across many entry points.

## Section Owners

| Need | Owner |
|------|-------|
| Docs index | [docs/README.md](../README.md) |
| Agent drift control | [Drift control](DRIFT_CONTROL.md) |
| User workflow | [Getting Started](../GETTING_STARTED.md) |
| Enterprise scope | [Positioning](../POSITIONING.md) |
| Developer workflow | [Developer Docs](../README.md#developer-docs) |
| Repo records | [Repo Hygiene And Project Record](../README.md#repo-hygiene-and-project-record) |
| Java framework docs | [Java Enterprise Framework Guides](../README.md#java-enterprise-framework-guides) |

## Developer Docs

| Change | Owner |
|--------|-------|
| Java construct rule | [Rule authoring](../developer/RULE_AUTHORING.md) |
| Translation module ownership | [Translation internals](../developer/TRANSLATION_INTERNALS.md) |
| Parser/analyzer | [Parser and analyzer](../developer/PARSER_ANALYZER.md) |
| Diagnostics/confidence/TODOs | [Diagnostics](../developer/DIAGNOSTICS.md) |
| Framework plugins | [Framework plugin authoring](../developer/FRAMEWORK_PLUGIN_AUTHORING.md) |
| Wiring targets | [Wiring targets](../developer/WIRING_TARGETS.md) |
| LLM providers/prompts | [LLM providers](../developer/LLM_PROVIDERS.md) |
| Validation gates | [Validation gates](../developer/VALIDATION_GATES.md) |
| VS Code extension | [VS Code extension](../developer/VS_CODE_EXTENSION.md) |
| API compatibility | [API stability](../developer/API_STABILITY.md) |

## User Docs

| Behavior changed | Update |
|------------------|--------|
| Main overview or quick start | root `README.md`, [Getting Started](../GETTING_STARTED.md), [docs/README.md](../README.md) |
| CLI command/option/JSON | [CLI](../CLI.md) |
| Python API/result model | [API guide](../API.md), [API reference](../API_REFERENCE.md) |
| Config schema/discovery | [Configuration](../CONFIGURATION.md), [CLI](../CLI.md) |
| Generated-output review | [Output review](../OUTPUT_REVIEW.md) |
| Doctor assessment/report | [Assessment](../ASSESSMENT.md), [Doctor](../DOCTOR.md) |
| SARIF export | [SARIF](../SARIF.md) |
| `j2py-wire` | [Wiring](../WIRING.md), [CLI](../CLI.md#j2py-wire) |
| VS Code extension | [VS Code support](../VS_CODE.md), `packages/j2py-vscode/README.md` |
| Spring behavior | [Spring conversion](../SPRING_CONVERSION.md), [Spring wiring metadata](../SPRING_WIRING_METADATA.md), [Spring cookbook](../examples/SPRING_MAPPING_COOKBOOK.md) |

## Repo Records

| Need | Owner |
|------|-------|
| Product scope | [Product requirements](../PRODUCT_REQUIREMENTS.md) |
| Doctor product roadmap | [Doctor product requirements](../DOCTOR_PRODUCT_REQUIREMENTS.md) |
| Release claims | [Release notes](../RELEASE_NOTES_0.7.0.md) |
| Release test evidence | [Release test evidence](../RELEASE_TEST_EVIDENCE_0.7.0.md) |
| Package evidence | [Release candidate evidence](../RELEASE_CANDIDATE_EVIDENCE_0.7.0.md) |
| Release docs audit | [Release documentation audit](../RELEASE_DOCUMENTATION_AUDIT_0.7.0.md) |
| Performance baseline | [Release performance baseline](../RELEASE_PERFORMANCE_BASELINE_0.7.0.md) |
| Diagnostics wording audit | [Release diagnostics TODO audit](../RELEASE_DIAGNOSTICS_TODO_AUDIT_0.7.0.md) |
| Case studies | [Tuple case study](../CASE_STUDY_COMMONS_LANG_TUPLE.md), [NumberUtils case study](../CASE_STUDY_COMMONS_LANG_NUMBER_UTILS.md) |

Repo records are snapshots. Verify current commands and metrics before citing them as
current evidence.

## Root Entrypoints

| File | Purpose | Sync with |
|------|---------|-----------|
| `README.md` | Public overview and quick start. | User docs, CLI examples. |
| `CONTRIBUTING.md` | Human contributor workflow. | Developer docs, validation gates. |
| `AGENTS.md` | Agent operating guidance. | `CLAUDE.md`, this section. |
| `CLAUDE.md` | Mirrored agent guidance. | `AGENTS.md`. |
| `SECURITY.md` | Vulnerability reporting. | Security policy only. |
| `CHANGELOG.md` | Version history. | User-visible changes. |
