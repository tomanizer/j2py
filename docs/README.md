# j2py documentation index

## Product and architecture

| Document | Description |
|----------|-------------|
| [INSTALL.md](INSTALL.md) | Package install, optional extras, API keys, JDK/corpus setup, common install issues |
| [GETTING_STARTED.md](GETTING_STARTED.md) | First-run workflow: assess, configure, translate, review, and measure |
| [CLI.md](CLI.md) | Command reference for `translate`, `analyze`, `compare`, `watch`, `dashboard`, `doctor`, and `sarif` |
| [OUTPUT_REVIEW.md](OUTPUT_REVIEW.md) | How to review confidence, warnings, TODO markers, validation, and generated reports |
| [API.md](API.md) | Python API usage for file/directory translation, config loading, diagnostics, and reports |
| [PRD.md](PRD.md) | Product goals, functional requirements, non-goals, success criteria |
| [SPRING_CONVERSION.md](SPRING_CONVERSION.md) | Practical Spring conversion workflow: config, sidecars, `j2py-wire`, smoke tests, and corpus checks |
| [SPRING_EXTENSION_PRD.md](SPRING_EXTENSION_PRD.md) | Optional Spring conversion extension scope, v1 target, and boundary rules |
| [SPRING_ROADMAP_GUARDRAILS.md](SPRING_ROADMAP_GUARDRAILS.md) | Guardrails and review checklist for Spring roadmap implementation work |
| [SPRING_WIRING_METADATA.md](SPRING_WIRING_METADATA.md) | Spring metadata profile stored under existing framework sidecars for `j2py-wire` |
| [POSITIONING.md](POSITIONING.md) | Useful scope, enterprise framework boundaries, and how to read corpus metrics |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline stages, module responsibilities, ADR index |
| [configuration.md](configuration.md) | Config file schema (`j2py.yaml`, TOML, pyproject) |
| [FRAMEWORK_PLUGINS.md](FRAMEWORK_PLUGINS.md) | Tier 4 framework plugin guide, quick start, and Spring migration example |
| [DOCTOR.md](DOCTOR.md) | `j2py doctor` assessment command, report schema, workflows, and limits |
| [DOCTOR_PRD.md](DOCTOR_PRD.md) | Product requirements and roadmap for project assessment tooling |
| [SARIF.md](SARIF.md) | `j2py sarif` export for doctor assessment diagnostics and code-scanning workflows |
| [RELEASE_DOCS_AUDIT_0.7.0.md](RELEASE_DOCS_AUDIT_0.7.0.md) | 0.7.0 docs audit against live CLI help, config schema, fixtures, and generated output |

## Quality, measurement, and roadmap

| Document | Description |
|----------|-------------|
| [TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) | Graduated vs future xfail construct workflow |
| [LLM_HARVEST.md](LLM_HARVEST.md) | LLM harvest: batch runs, triage, content cache, promotion pipeline, GitHub issues |
| [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md) | Multi-library corpus presets, baselines, hotspots |
| [EQUIVALENCE_TESTING.md](EQUIVALENCE_TESTING.md) | Differential testing design and current equivalence-verified public-surface floor |
| [BEHAVIOR_CORPUS.md](BEHAVIOR_CORPUS.md) | JDK-backed stdout/exit-code behavior suite |
| [PERFORMANCE_BASELINE_0.7.0.md](PERFORMANCE_BASELINE_0.7.0.md) | 0.7.0 local translation, Spring smoke, and corpus reporting performance baseline |
| [RELEASE_TEST_COVERAGE_0.7.0.md](RELEASE_TEST_COVERAGE_0.7.0.md) | 0.7.0 release-facing claim-to-evidence inventory |
| [CASE_STUDY.md](CASE_STUDY.md) | End-to-end multi-file case study (commons-lang `tuple`): what translated, gaps surfaced |
| [CASE_STUDY_NUMBER_UTILS.md](CASE_STUDY_NUMBER_UTILS.md) | End-to-end NumberUtils equivalence case study: verified surface, stubs, and exclusions |
| [RELEASE_NOTES_0.7.0.md](RELEASE_NOTES_0.7.0.md) | 0.7.0 release-note draft, user-facing scope, quality evidence, and known limits |

## Process and release

| Document | Description |
|----------|-------------|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Branch workflow, fixtures, material-change rules |
| [../CHANGELOG.md](../CHANGELOG.md) | Version history |
| [RELEASING.md](RELEASING.md) | Beta/pre-release checklist |
| [../SECURITY.md](../SECURITY.md) | Vulnerability reporting |

## Architecture decisions and audits

| Document | Description |
|----------|-------------|
| [decisions/0001-record-architecture-decisions.md](decisions/0001-record-architecture-decisions.md) | ADR process template |
| [ARCHITECTURE.md#key-design-decisions](ARCHITECTURE.md#key-design-decisions) | ADRs 0002–0024 (parser, pipeline, LLM providers, overloads, equivalence, framework boundaries, ...) |
| [decisions/AUDIT-2026-06-17.md](decisions/AUDIT-2026-06-17.md) | Latest dated maturity and gap audit snapshot |
| [decisions/AUDIT-2026-06-15.md](decisions/AUDIT-2026-06-15.md) | Prior maturity and gap audit snapshot |
| [decisions/AUDIT-2026-06-13.md](decisions/AUDIT-2026-06-13.md) | Earliest rule-layer breadth snapshot |

## Agent onboarding

| Document | Description |
|----------|-------------|
| [../AGENTS.md](../AGENTS.md) | Agent guidance (mirrored in `CLAUDE.md`) |
| [../.cursor/skills/README.md](../.cursor/skills/README.md) | Cursor agent skills (harvest promotion, etc.) |
| [../packages/j2py-vscode/README.md](../packages/j2py-vscode/README.md) | VS Code extension commands, settings, and VSIX build notes |
