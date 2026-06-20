# j2py documentation index

The docs are split by audience, with a separate section for source-framework-specific
guides. File paths are kept flat so existing links stay stable, but the index should help
readers start in the right place.

Start here:

- New users: [Getting Started](GETTING_STARTED.md)
- Enterprise migrations: [Assessment](ASSESSMENT.md), [Configuration](CONFIGURATION.md), [Wiring](WIRING.md)
- Contributors: [Developer Docs](#developer-docs)
- Coding agents: [Coding Agent Guides](agents/README.md)

## User Docs

Use these when you are installing j2py, assessing a Java project, configuring
translation, reviewing output, or using framework/wiring layers. The important message is
that these are not separate products. See
[the pipeline overview](POSITIONING.md#one-pipeline-five-layers) for how the layers fit
together.

Choose the path that matches your project:

| Path | Use it when | Read first |
|------|-------------|------------|
| First run | You want to install j2py and translate one small file. | [Getting Started](GETTING_STARTED.md), [Install](INSTALL.md) |
| Simple Java | You have plain Java classes and want reviewable Python. | [Getting Started](GETTING_STARTED.md), [CLI](CLI.md), [Output review](OUTPUT_REVIEW.md) |
| Project migration | You need to assess a source tree, tune mappings, and review risk. | [Assessment](ASSESSMENT.md), [Configuration](CONFIGURATION.md), [Output review](OUTPUT_REVIEW.md) |
| Framework migration | You need framework metadata, sidecars, and generated app wiring. | [Framework plugins](FRAMEWORK_PLUGINS.md), [Wiring](WIRING.md), [Java Enterprise Framework Guides](#java-enterprise-framework-guides) |
| Automation | You want to call j2py from scripts or tooling. | [API guide](API.md), [API reference](API_REFERENCE.md), [CLI](CLI.md) |
| Editor review | You want side-by-side review or editor diagnostics. | [Output review](OUTPUT_REVIEW.md), [VS Code support](VS_CODE.md) |

For commands, use the [simple path](GETTING_STARTED.md#simple-path) or
[enterprise path](GETTING_STARTED.md#enterprise-path) in Getting Started.

Core user references:

| Document | What it helps with |
|----------|--------------------|
| [INSTALL.md](INSTALL.md) | Install j2py, optional extras, API keys, JDK/corpus prerequisites, and common install issues. |
| [GETTING_STARTED.md](GETTING_STARTED.md) | First usable workflow from install through assessment, config, translation, review, LLM use, and optional Spring wiring. |
| [POSITIONING.md](POSITIONING.md) | What j2py is good for, enterprise framework boundaries, and how the pipeline fits together. |
| [CLI.md](CLI.md) | Command reference for `translate`, `analyze`, `compare`, `watch`, `dashboard`, `doctor`, `sarif`, and `j2py-wire`. |
| [OUTPUT_REVIEW.md](OUTPUT_REVIEW.md) | How to review confidence, warnings, TODOs, validation, structural verification, reports, and benchmark deltas. |

Advanced user references:

| Document | What it helps with |
|----------|--------------------|
| [CONFIGURATION.md](CONFIGURATION.md) | Project policy for names, imports, types, annotations, LLM defaults, and trusted plugin registration. |
| [FRAMEWORK_PLUGINS.md](FRAMEWORK_PLUGINS.md) | Trusted opt-in framework metadata extraction and source transforms. |
| [WIRING.md](WIRING.md) | `j2py-wire` sidecar inspection, target-stack generation, validation, and review. |
| [ASSESSMENT.md](ASSESSMENT.md) | How to use `j2py doctor` to assess migration readiness and guide config/rule work. |
| [DOCTOR.md](DOCTOR.md) | Detailed `j2py doctor` command reference, schema, report, diff, and config-suggestion behavior. |
| [SARIF.md](SARIF.md) | Export doctor findings to SARIF for code-scanning workflows. |
| [VS_CODE.md](VS_CODE.md) | Experimental VS Code support, extension behavior, Copilot/Sonar integration ideas, and validation checklist. |
| [API.md](API.md) | Practical Python API guide for file/directory translation, config loading, diagnostics, and reports. |
| [API_REFERENCE.md](API_REFERENCE.md) | Reference for supported Python imports, function signatures, result models, and stability levels. |

Common user-facing tasks:

| Task | Surface | Start here |
|------|---------|------------|
| Install j2py and optional extras | `pip install --pre j2py-converter[...]` | [Install](INSTALL.md) |
| Translate one file or a source tree | `j2py translate` | [Getting Started](GETTING_STARTED.md), [CLI](CLI.md#j2py-translate) |
| Inspect Java classes before translating | `j2py analyze` | [CLI](CLI.md#j2py-analyze) |
| Review Java and Python side by side | `j2py compare`, `j2py translate --report` | [Output review](OUTPUT_REVIEW.md), [CLI](CLI.md#j2py-compare) |
| Create or refresh dashboard reports | `j2py translate --dashboard`, `j2py dashboard` | [Output review](OUTPUT_REVIEW.md), [CLI](CLI.md#j2py-dashboard) |
| Re-translate while editing | `j2py watch` | [CLI](CLI.md#j2py-watch) |
| Review in VS Code | `j2py compare`, experimental `packages/j2py-vscode` extension | [VS Code support](VS_CODE.md), [Output review](OUTPUT_REVIEW.md) |
| Run rule-only assessment | `j2py doctor --json --html` | [Assessment](ASSESSMENT.md), [Doctor](DOCTOR.md) |
| Compare assessment snapshots | `j2py doctor diff before.json after.json` | [Assessment](ASSESSMENT.md#outputs), [Doctor](DOCTOR.md) |
| Generate conservative config suggestions | `j2py doctor --config-suggestions j2py.suggested.yaml` | [Assessment](ASSESSMENT.md#config-suggestions), [Configuration](CONFIGURATION.md) |
| Export diagnostics to code scanning | `j2py sarif` | [SARIF](SARIF.md) |
| Configure project mappings and LLM defaults | `j2py.toml`, `j2py_config.py` | [Configuration](CONFIGURATION.md) |
| Use LLM completion or LLM review | `--llm-provider`, `--model`, `--llm-review` | [Getting Started](GETTING_STARTED.md#8-add-llm-completion-deliberately), [Output review](OUTPUT_REVIEW.md#llm-review-findings) |
| Validate generated Python | `--validate`, `j2py-converter[validate]` | [Install](INSTALL.md), [Output review](OUTPUT_REVIEW.md#validation) |
| Generate app wiring from sidecars | `j2py-wire list/generate/validate` | [Wiring](WIRING.md) |
| Embed j2py in scripts | `j2py.pipeline`, `TranslationConfig` | [API guide](API.md), [API reference](API_REFERENCE.md) |

## Java Enterprise Framework Guides

Use this section only when your source project uses one of these Java enterprise
frameworks. The general j2py docs above are framework-neutral; framework-specific guides
add source-framework context, metadata profiles, examples, and boundary rules.

### Spring

Spring users should start here:

| Document | What it helps with |
|----------|--------------------|
| [SPRING_CONVERSION.md](SPRING_CONVERSION.md) | Practical Spring conversion workflow: config, sidecars, `j2py-wire`, smoke tests, and corpus checks. |
| [SPRING_WIRING_METADATA.md](SPRING_WIRING_METADATA.md) | Spring metadata profile stored under generic framework sidecars for `j2py-wire`. |
| [examples/SPRING_MAPPING_COOKBOOK.md](examples/SPRING_MAPPING_COOKBOOK.md) | Spring -> FastAPI/SQLAlchemy mapping examples, manual-port boundaries, and reference config notes. |
| [examples/spring-to-fastapi.toml](examples/spring-to-fastapi.toml) | TOML reference profile for Spring-style annotation mapping. |
| [examples/spring-to-fastapi.yaml](examples/spring-to-fastapi.yaml) | YAML reference profile for Spring-style annotation mapping. |

Spring maintainers and contributors should also read:

| Document | What it records |
|----------|-----------------|
| [SPRING_EXTENSION_PRD.md](SPRING_EXTENSION_PRD.md) | Optional Spring conversion extension scope, v1 target, and boundary rules. |
| [SPRING_ROADMAP_GUARDRAILS.md](SPRING_ROADMAP_GUARDRAILS.md) | Guardrails and review checklist for Spring roadmap implementation work. |

Future framework guides, such as Jakarta EE, JAX-RS, Micronaut, or Quarkus, should be added
as sibling subsections here rather than mixed into the general User Docs table.

## Developer Docs

Use these when you are improving j2py itself. Start from the kind of change you are
making, then read the deeper reference docs and run the matching validation gate. `make
check` remains the default local gate for normal code changes; narrower commands are
listed where they give faster or more specific evidence.

Read order:

1. New contributor: [CONTRIBUTING](../CONTRIBUTING.md) -> [Architecture](ARCHITECTURE.md).
2. Specific change: use the task map below.
3. Broad design or settled policy: check the ADR index in [Architecture](ARCHITECTURE.md).
4. Release evidence, audits, and historical scorecards: use
   [Repo Hygiene And Project Record](#repo-hygiene-and-project-record), not the task map.

Choose the path that matches the change:

| Path | Use it when | Read first |
|------|-------------|------------|
| New contributor | You need repo workflow, fixture expectations, and architecture context. | [Contributing](../CONTRIBUTING.md), [Architecture](ARCHITECTURE.md) |
| Rule-layer contributor | You are adding Java construct coverage or changing generated Python semantics. | [Rule authoring](developer/RULE_AUTHORING.md), [Translation internals](developer/TRANSLATION_INTERNALS.md), [Validation gates](developer/VALIDATION_GATES.md) |
| Assessment/tooling contributor | You are changing doctor, validation, SARIF, reports, or confidence behavior. | [Diagnostics guide](developer/DIAGNOSTICS.md), [Assessment](ASSESSMENT.md), [Output review](OUTPUT_REVIEW.md) |
| Framework/wiring contributor | You are changing plugins, sidecars, or generated target-stack wiring. | [Framework plugin authoring](developer/FRAMEWORK_PLUGIN_AUTHORING.md), [Wiring target guide](developer/WIRING_TARGETS.md) |
| API/CLI contributor | You are changing public imports, result models, or command behavior. | [API stability](developer/API_STABILITY.md), [CLI](CLI.md), [API reference](API_REFERENCE.md) |
| LLM contributor | You are changing providers, prompts, caches, retries, or harvest behavior. | [LLM providers](developer/LLM_PROVIDERS.md), [LLM harvest](LLM_HARVEST.md) |
| Editor contributor | You are changing the experimental VS Code extension. | [VS Code extension guide](developer/VS_CODE_EXTENSION.md), [VS Code support](VS_CODE.md) |

| If you are doing this | Read | Validation |
|-----------------------|------|------------|
| Route a coding-agent change | [Coding agent guides](agents/README.md), [Change routing](agents/CHANGE_ROUTING.md), [Validation matrix](agents/VALIDATION_MATRIX.md) | Use the gate selected by the validation matrix; for docs changes also run `pytest tests/test_docs_links.py -q`. |
| Change parser, analyzer, or symbol graph behavior | [Parser/analyzer guide](developer/PARSER_ANALYZER.md), [Architecture](ARCHITECTURE.md), relevant parser/analyzer ADRs | `pytest tests/parse tests/analyze -q`; add corpus checks when dependency ordering or symbol extraction changes. |
| Add a Java construct rule | [Rule authoring](developer/RULE_AUTHORING.md), [Translation internals](developer/TRANSLATION_INTERNALS.md), [Translation targets](TRANSLATION_TARGETS.md), [Architecture](ARCHITECTURE.md) | Java/Python fixture tests, `make check`, relevant corpus dense check. |
| Change runtime helpers, validation, imports, or platform/JDK boundaries | [Translation internals](developer/TRANSLATION_INTERNALS.md), [Diagnostics guide](developer/DIAGNOSTICS.md), [Output review](OUTPUT_REVIEW.md), [ADR 0020](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md) | `pytest tests/validate tests/translate/test_platform_imports.py tests/translate/test_runtime_dispatch.py -q`; behavior/equivalence tests when runtime semantics change. |
| Add equivalence coverage | [Equivalence testing](EQUIVALENCE_TESTING.md), [Behavior corpus](BEHAVIOR_CORPUS.md) | `make test-equivalence`, `make equivalence-report`; `make test-behavior` when JDK behavior fixtures change. |
| Harvest new gaps | [LLM harvest](LLM_HARVEST.md), [Translation targets](TRANSLATION_TARGETS.md) | Harvest triage, future target or promoted fixture, GitHub issue when the pattern is backlog-sized. |
| Change configuration behavior | [Configuration](CONFIGURATION.md), [CLI](CLI.md), [API](API.md) | `pytest tests/config tests/translate/skeleton/test_config.py tests/cli/test_main.py -q`. |
| Change CLI or Python API behavior | [API stability](developer/API_STABILITY.md), [CLI](CLI.md), [API guide](API.md), [API reference](API_REFERENCE.md), [Architecture](ARCHITECTURE.md) | `pytest tests/cli/test_main.py tests/test_pipeline.py -q`. |
| Change LLM provider behavior | [LLM providers](developer/LLM_PROVIDERS.md), [Install](INSTALL.md), [Configuration](CONFIGURATION.md), [API guide](API.md), [API reference](API_REFERENCE.md), [LLM harvest](LLM_HARVEST.md) | `pytest tests/llm tests/cli/test_main.py -q`; live provider tests only when explicitly requested. |
| Change framework/plugin behavior | [Framework plugin authoring](developer/FRAMEWORK_PLUGIN_AUTHORING.md), [Framework plugins](FRAMEWORK_PLUGINS.md), relevant [Java Enterprise Framework Guides](#java-enterprise-framework-guides), relevant ADRs | Plugin tests, sidecar fixture tests, relevant framework corpus or smoke gate. |
| Change wiring targets | [Wiring target guide](developer/WIRING_TARGETS.md), [Wiring](WIRING.md), [CLI](CLI.md#j2py-wire) | `pytest tests/wire -q`. |
| Change doctor/SARIF | [Diagnostics guide](developer/DIAGNOSTICS.md), [Assessment](ASSESSMENT.md), [Doctor](DOCTOR.md), [SARIF](SARIF.md) | `pytest tests/test_doctor.py tests/test_sarif.py -q`. |
| Change reports, dashboards, or review output | [Output review](OUTPUT_REVIEW.md), [CLI](CLI.md), [Assessment](ASSESSMENT.md) | `pytest tests/test_report.py tests/test_state_dashboard.py tests/cli/test_main.py -q`. |
| Change corpus/reporting | [Corpus scoreboard](CORPUS_SCOREBOARD.md), [Translation targets](TRANSLATION_TARGETS.md) | Relevant `make corpus-<name>-dense-check`, `make corpus-hotspots`; update baselines only after no-regression review. |
| Change packaging, install extras, or dependency metadata | [Install](INSTALL.md), [Releasing](RELEASING.md), [Contributing](../CONTRIBUTING.md) | `pytest tests/packaging -q`, `make release-check` when release packaging is affected. |
| Change docs or release evidence | [Documentation index](README.md), relevant user/developer doc, [Release docs audit](releases/0.7.0/DOCUMENTATION_AUDIT.md) | `pytest tests/test_release_coverage_inventory.py tests/test_release_candidate_checklist.py tests/test_release_diagnostics_todo_audit.py tests/test_release_performance_baseline.py tests/packaging/test_check_sdist_hygiene.py -q`. |
| Release | [Releasing](RELEASING.md), [Changelog](../CHANGELOG.md) | `make release-check` plus publish verification. |
| Work on VS Code | [VS Code extension guide](developer/VS_CODE_EXTENSION.md), [VS Code support](VS_CODE.md), [extension README](../packages/j2py-vscode/README.md) | `npm ci`, `npm run compile`, VSIX smoke test. |

Developer change guides:

Start with [developer/README.md](developer/README.md) for the guide index.

Coding-agent guides:

| Guide | What it helps with |
|-------|--------------------|
| [agents/README.md](agents/README.md) | Agent-oriented entry point for change routing, validation, docs map, and common failures. |
| [agents/CHANGE_ROUTING.md](agents/CHANGE_ROUTING.md) | Map task types to owner modules, human docs, and validation gates. |
| [agents/DRIFT_CONTROL.md](agents/DRIFT_CONTROL.md) | Search-before-create rules to avoid duplicate helpers, docs, commands, and processes. |
| [agents/VALIDATION_MATRIX.md](agents/VALIDATION_MATRIX.md) | Compact validation matrix for focused, semantic, corpus, live, and docs gates. |
| [agents/DOCS_MAP.md](agents/DOCS_MAP.md) | Map public behavior changes to the docs that must be checked or updated. |
| [agents/COMMON_FAILURES.md](agents/COMMON_FAILURES.md) | Common coding-agent mistakes to check before finalizing. |

Core translation:

| Guide | What it helps with |
|-------|--------------------|
| [developer/RULE_AUTHORING.md](developer/RULE_AUTHORING.md) | Adding deterministic Java construct rules with fixtures, diagnostics, and gates. |
| [developer/PARSER_ANALYZER.md](developer/PARSER_ANALYZER.md) | Changing `JavaNode`, tree-sitter parser behavior, symbol extraction, and dependency analysis. |
| [developer/TRANSLATION_INTERNALS.md](developer/TRANSLATION_INTERNALS.md) | Translation module ownership and when to add a rule, helper, runtime shim, or diagnostic. |
| [developer/DIAGNOSTICS.md](developer/DIAGNOSTICS.md) | Diagnostic IDs, semantic warnings, TODO markers, confidence, doctor output, and SARIF. |

Frameworks and app assembly:

| Guide | What it helps with |
|-------|--------------------|
| [developer/FRAMEWORK_PLUGIN_AUTHORING.md](developer/FRAMEWORK_PLUGIN_AUTHORING.md) | Writing trusted framework plugins with translated-output and sidecar tests. |
| [developer/WIRING_TARGETS.md](developer/WIRING_TARGETS.md) | Adding or changing `j2py-wire --target` generators and validation checks. |

Tooling and public surfaces:

| Guide | What it helps with |
|-------|--------------------|
| [developer/LLM_PROVIDERS.md](developer/LLM_PROVIDERS.md) | Provider calls, prompts, cache keys, retries, optional extras, and live-test boundaries. |
| [developer/VALIDATION_GATES.md](developer/VALIDATION_GATES.md) | Choosing the right local Makefile or pytest gate for a change. |
| [developer/VS_CODE_EXTENSION.md](developer/VS_CODE_EXTENSION.md) | Extension commands, settings, diagnostics, compile/package flow, and smoke testing. |
| [developer/API_STABILITY.md](developer/API_STABILITY.md) | Public, facade, experimental, and internal API stability expectations. |

Reference docs:

| Document | What it helps with |
|----------|--------------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline stages, module responsibilities, data flow, and ADR index. |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Branch workflow, fixture expectations, material-change rules, and PR conventions. |
| [TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) | Graduated vs future xfail construct workflow for deterministic rule-layer backlog. |
| [EQUIVALENCE_TESTING.md](EQUIVALENCE_TESTING.md) | Differential testing design and current equivalence-verified public-surface floor. |
| [BEHAVIOR_CORPUS.md](BEHAVIOR_CORPUS.md) | JDK-backed stdout/exit-code behavior suite. |
| [ADR 0020](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md) | Policy for JDK lowering, runtime helpers, and platform boundary stubs. |
| [CONFIGURATION.md](CONFIGURATION.md) | Project policy schema, config loading, mappings, LLM defaults, and plugin registration. |
| [FRAMEWORK_PLUGINS.md](FRAMEWORK_PLUGINS.md) | Trusted plugin authoring for framework metadata and source transforms. |
| [WIRING.md](WIRING.md) | `j2py-wire` target generation, sidecar loading, and validation. |
| [ASSESSMENT.md](ASSESSMENT.md), [DOCTOR.md](DOCTOR.md), [SARIF.md](SARIF.md) | Assessment, doctor reports, diffs, config suggestions, and code-scanning export. |
| [LLM_HARVEST.md](LLM_HARVEST.md) | LLM harvest: batch runs, triage, content cache, promotion to targets and GitHub issues. |
| [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md) | Multi-library corpus presets, baselines, hotspot reports, and dense-check workflow. |
| [CLI.md](CLI.md), [API.md](API.md), [API_REFERENCE.md](API_REFERENCE.md), [OUTPUT_REVIEW.md](OUTPUT_REVIEW.md) | Command/API surfaces and generated-output review artifacts. |
| [INSTALL.md](INSTALL.md) | Optional extras, provider dependencies, validation tools, and environment prerequisites. |
| [RELEASING.md](RELEASING.md) | Beta/pre-release checklist and publish verification workflow. |
| [VS_CODE.md](VS_CODE.md) and [../packages/j2py-vscode/README.md](../packages/j2py-vscode/README.md) | Experimental VS Code support, extension commands, settings, limitations, and VSIX build notes. |
| [../.cursor/skills/README.md](../.cursor/skills/README.md) | Cursor agent skills, including harvest promotion workflows. |

## Repo Hygiene And Project Record

Use this section when you need the project record rather than the current user or
developer workflow. These documents explain why the project behaves the way it does, what
evidence backed a release, and what decisions or audits shaped the repo.

Do not treat old release notes, case studies, or audits as the current command reference.
Use the User Docs and Developer Docs sections above for current workflows.

Quick lookup:

| Question | Start here |
|----------|------------|
| What is j2py supposed to be? | [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) |
| What is `j2py doctor` supposed to become? | [DOCTOR_PRODUCT_REQUIREMENTS.md](DOCTOR_PRODUCT_REQUIREMENTS.md) |
| What did a release claim and prove? | [releases/0.7.0/RELEASE_NOTES.md](releases/0.7.0/RELEASE_NOTES.md), [releases/0.7.0/TEST_EVIDENCE.md](releases/0.7.0/TEST_EVIDENCE.md) |
| What package/install evidence backed a release? | [releases/0.7.0/CANDIDATE_EVIDENCE.md](releases/0.7.0/CANDIDATE_EVIDENCE.md) |
| What docs were audited for a release? | [releases/0.7.0/DOCUMENTATION_AUDIT.md](releases/0.7.0/DOCUMENTATION_AUDIT.md) |
| What performance or diagnostics evidence backed a release? | [releases/0.7.0/PERFORMANCE_BASELINE.md](releases/0.7.0/PERFORMANCE_BASELINE.md), [releases/0.7.0/DIAGNOSTICS_TODO_AUDIT.md](releases/0.7.0/DIAGNOSTICS_TODO_AUDIT.md) |
| How did j2py behave on representative code? | [CASE_STUDY_COMMONS_LANG_TUPLE.md](CASE_STUDY_COMMONS_LANG_TUPLE.md), [CASE_STUDY_COMMONS_LANG_NUMBER_UTILS.md](CASE_STUDY_COMMONS_LANG_NUMBER_UTILS.md) |
| Why was an architecture choice made? | [Architecture decisions](#architecture-decisions) |
| What did earlier maturity audits say? | [Audit Snapshots](#audit-snapshots) |

Naming convention:

| Prefix or pattern | Use for |
|-------------------|---------|
| `PRODUCT_*` | Product scope, roadmap, and requirements records. |
| `releases/<version>/*.md` | Versioned release evidence snapshots. |
| `CASE_STUDY_<subject>.md` | Narrative evidence from representative source code. |
| `decisions/NNNN-*.md` | Accepted architecture decision records. |
| `decisions/AUDIT-YYYY-MM-DD.md` | Dated maturity or gap audits. |

### Product And Roadmap Record

| Document | What it records |
|----------|-----------------|
| [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) | Product goals, functional requirements, non-goals, and success criteria. |
| [DOCTOR_PRODUCT_REQUIREMENTS.md](DOCTOR_PRODUCT_REQUIREMENTS.md) | Product requirements and roadmap for project assessment tooling. |

### Release Evidence

Use these when checking what was claimed, tested, measured, or still known-limited for a
specific release. They are evidence snapshots, not the live command reference.

| Document | What it records |
|----------|-----------------|
| [releases/0.7.0/RELEASE_NOTES.md](releases/0.7.0/RELEASE_NOTES.md) | 0.7.0 release-note draft, user-facing scope, quality evidence, and known limits. |
| [releases/0.7.0/CANDIDATE_EVIDENCE.md](releases/0.7.0/CANDIDATE_EVIDENCE.md) | 0.7.0 package build, clean install smoke, and pre-tag checklist evidence. |
| [releases/0.7.0/DOCUMENTATION_AUDIT.md](releases/0.7.0/DOCUMENTATION_AUDIT.md) | 0.7.0 docs audit against live CLI help, config schema, fixtures, and generated output. |
| [releases/0.7.0/TEST_EVIDENCE.md](releases/0.7.0/TEST_EVIDENCE.md) | Release-facing claim-to-evidence inventory for 0.7.0. |
| [releases/0.7.0/PERFORMANCE_BASELINE.md](releases/0.7.0/PERFORMANCE_BASELINE.md) | Local translation, Spring smoke, and corpus reporting performance baseline for 0.7.0. |
| [releases/0.7.0/DIAGNOSTICS_TODO_AUDIT.md](releases/0.7.0/DIAGNOSTICS_TODO_AUDIT.md) | Diagnostics and TODO wording audit for framework and platform boundaries. |

### Case Studies

Use these for narrative examples of how j2py behaved on representative code at a point in
time. They are useful for understanding tradeoffs and evidence style.

| Document | What it records |
|----------|-----------------|
| [CASE_STUDY_COMMONS_LANG_TUPLE.md](CASE_STUDY_COMMONS_LANG_TUPLE.md) | End-to-end multi-file case study for commons-lang `tuple`. |
| [CASE_STUDY_COMMONS_LANG_NUMBER_UTILS.md](CASE_STUDY_COMMONS_LANG_NUMBER_UTILS.md) | NumberUtils equivalence case study: verified surface, stubs, and exclusions. |

### Repo Governance And Operations

Use these for repo-level policy, release history, security reporting, and agent operating
rules.

| Document | What it records |
|----------|-----------------|
| [../CHANGELOG.md](../CHANGELOG.md) | Version history. |
| [../SECURITY.md](../SECURITY.md) | Vulnerability reporting. |
| [../AGENTS.md](../AGENTS.md) | Agent guidance, mirrored in `CLAUDE.md`. |

### Architecture Decisions

Use these when changing settled design policy. ADRs record decisions; they are not
implementation tickets and should not be reversed without a new ADR.

| Document | What it records |
|----------|-----------------|
| [decisions/0001-record-architecture-decisions.md](decisions/0001-record-architecture-decisions.md) | ADR process template. |
| [ARCHITECTURE.md#key-design-decisions](ARCHITECTURE.md#key-design-decisions) | ADRs 0002-0025: parser, pipeline, LLM providers, overloads, equivalence, framework boundaries, PetClinic smoke gate, and related decisions. |

### Audit Snapshots

Use these when comparing current maturity with prior audits. Audit files are dated
snapshots; verify current commands, metrics, and test results before using them as
evidence for a new change.

| Document | What it records |
|----------|-----------------|
| [decisions/AUDIT-2026-06-17.md](decisions/AUDIT-2026-06-17.md) | Latest dated maturity and gap audit snapshot. |
| [decisions/AUDIT-2026-06-15.md](decisions/AUDIT-2026-06-15.md) | Prior maturity and gap audit snapshot. |
| [decisions/AUDIT-2026-06-13.md](decisions/AUDIT-2026-06-13.md) | Earliest rule-layer breadth snapshot. |
