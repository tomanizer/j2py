# j2py documentation index

Start here:

- New users: [Getting Started](GETTING_STARTED.md)
- Enterprise migrations: [Doctor](DOCTOR.md), [Configuration](CONFIGURATION.md), [Wiring](WIRING.md)
- Contributors: [Developer Docs](developer/README.md)
- Coding agents: [Coding Agent Guides](agents/README.md)

## User Docs

| Document | What it helps with |
|----------|--------------------|
| [INSTALL.md](INSTALL.md) | Install j2py, optional extras, API keys, validation tools, JDK/corpus prerequisites, and common install issues. |
| [GETTING_STARTED.md](GETTING_STARTED.md) | First usable workflow from install through assessment, config, translation, review, LLM use, and optional Spring wiring. |
| [POSITIONING.md](POSITIONING.md) | What j2py is good for, what it is not, enterprise framework boundaries, and how the pipeline layers fit together. |
| [CLI.md](CLI.md) | Command reference for `translate`, `analyze`, `compare`, `watch`, `dashboard`, `doctor`, `sarif`, and `j2py-wire`. |
| [OUTPUT_REVIEW.md](OUTPUT_REVIEW.md) | How to review confidence, warnings, TODOs, validation, structural verification, reports, and benchmark deltas. |
| [CONFIGURATION.md](CONFIGURATION.md) | Project policy for names, imports, types, annotations, LLM defaults, and trusted plugin registration. |
| [FRAMEWORK_PLUGINS.md](FRAMEWORK_PLUGINS.md) | Trusted opt-in framework metadata extraction and source transforms. |
| [WIRING.md](WIRING.md) | `j2py-wire` sidecar inspection, target-stack generation, validation, and review. |
| [DOCTOR.md](DOCTOR.md) | Assessment overview, `j2py doctor` command reference, schema, reports, diffs, config suggestions, and roadmap. |
| [SARIF.md](SARIF.md) | Export doctor findings to SARIF for code-scanning workflows. |
| [VS_CODE.md](VS_CODE.md) | Experimental VS Code support, extension behavior, Copilot/Sonar integration ideas, and validation checklist. |
| [API.md](API.md) | Practical Python API guide for file/directory translation, config loading, diagnostics, and reports. |
| [API_REFERENCE.md](API_REFERENCE.md) | Reference for supported Python imports, function signatures, result models, and stability levels. |

## Java Enterprise Framework Guides

Use this section only when your source project uses a Java enterprise framework. The
general j2py docs above are framework-neutral; framework-specific guides add
source-framework context, metadata profiles, examples, and boundary rules.

Spring users should start with [SPRING_CONVERSION.md](SPRING_CONVERSION.md) for the
workflow, sidecars, metadata profile, `j2py-wire`, smoke tests, and corpus checks.

Spring maintainers should also read [SPRING_DESIGN.md](SPRING_DESIGN.md) for scope,
boundary rules, implementation guardrails, and the review checklist.

Recipes and reference profiles live in
[examples/SPRING_MAPPING_COOKBOOK.md](examples/SPRING_MAPPING_COOKBOOK.md),
[examples/spring-to-fastapi.toml](examples/spring-to-fastapi.toml), and
[examples/spring-to-fastapi.yaml](examples/spring-to-fastapi.yaml).

Future framework guides, such as Jakarta EE, JAX-RS, Micronaut, or Quarkus, should be
added as sibling notes here rather than mixed into the general User Docs table.

## Developer Docs

| Document | What it helps with |
|----------|--------------------|
| [developer/README.md](developer/README.md) | Developer guide index by subsystem. |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Branch workflow, fixture expectations, material-change rules, and PR conventions. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline stages, module boundaries, data flow, and ADR index. |
| [developer/RULE_AUTHORING.md](developer/RULE_AUTHORING.md) | Adding deterministic Java construct rules with fixtures, diagnostics, and gates. |
| [developer/PARSER_ANALYZER.md](developer/PARSER_ANALYZER.md) | Changing `JavaNode`, tree-sitter parser behavior, symbol extraction, and dependency analysis. |
| [developer/TRANSLATION_INTERNALS.md](developer/TRANSLATION_INTERNALS.md) | Translation module ownership and when to add a rule, helper, runtime shim, or diagnostic. |
| [developer/DIAGNOSTICS.md](developer/DIAGNOSTICS.md) | Diagnostic IDs, semantic warnings, TODO markers, confidence, doctor output, and SARIF. |
| [developer/FRAMEWORK_PLUGIN_AUTHORING.md](developer/FRAMEWORK_PLUGIN_AUTHORING.md) | Writing trusted framework plugins with translated-output and sidecar tests. |
| [developer/WIRING_TARGETS.md](developer/WIRING_TARGETS.md) | Adding or changing `j2py-wire --target` generators and validation checks. |
| [developer/LLM_PROVIDERS.md](developer/LLM_PROVIDERS.md) | Provider calls, prompts, cache keys, retries, optional extras, and live-test boundaries. |
| [developer/VALIDATION_GATES.md](developer/VALIDATION_GATES.md) | Choosing the right local Makefile or pytest gate for a change. |
| [developer/VS_CODE_EXTENSION.md](developer/VS_CODE_EXTENSION.md) | Extension commands, settings, diagnostics, compile/package flow, and smoke testing. |
| [developer/API_STABILITY.md](developer/API_STABILITY.md) | Public, facade, experimental, and internal API stability expectations. |
| [agents/README.md](agents/README.md) | Agent-oriented entry point for change routing, validation, drift control, and common failures. |
| [agents/CHANGE_ROUTING.md](agents/CHANGE_ROUTING.md) | Map task types to owner modules, human docs, and validation gates. |
| [agents/DRIFT_CONTROL.md](agents/DRIFT_CONTROL.md) | Search-before-create rules to avoid duplicate helpers, docs, commands, and processes. |
| [agents/VALIDATION_MATRIX.md](agents/VALIDATION_MATRIX.md) | Compact validation matrix for focused, semantic, corpus, live, and docs gates. |
| [agents/COMMON_FAILURES.md](agents/COMMON_FAILURES.md) | Common coding-agent mistakes to check before finalizing. |

## Repo Hygiene and Project Record

| Document | What it records |
|----------|-----------------|
| [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) | Product goals, functional requirements, non-goals, and success criteria. |
| [TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) | Graduated vs future xfail construct workflow for deterministic rule-layer backlog. |
| [EQUIVALENCE_TESTING.md](EQUIVALENCE_TESTING.md) | Differential testing design and current equivalence-verified public-surface floor. |
| [BEHAVIOR_CORPUS.md](BEHAVIOR_CORPUS.md) | JDK-backed stdout/exit-code behavior suite. |
| [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md) | Multi-library corpus presets, baselines, hotspot reports, and dense-check workflow. |
| [LLM_HARVEST.md](LLM_HARVEST.md) | LLM harvest: batch runs, triage, content cache, promotion to targets and GitHub issues. |
| [CASE_STUDY_COMMONS_LANG_TUPLE.md](CASE_STUDY_COMMONS_LANG_TUPLE.md) | End-to-end multi-file case study for commons-lang `tuple`. |
| [CASE_STUDY_COMMONS_LANG_NUMBER_UTILS.md](CASE_STUDY_COMMONS_LANG_NUMBER_UTILS.md) | NumberUtils equivalence case study: verified surface, stubs, and exclusions. |
| [CASE_STUDY_JSEMVER.md](CASE_STUDY_JSEMVER.md) | First external end-to-end case study: java-semver translated and run against its own JUnit suite (#613). |
| [CASE_STUDY_COMMONS_CODEC_HEX.md](CASE_STUDY_COMMONS_CODEC_HEX.md) | Second external end-to-end case study: Apache Commons Codec `Hex` translated and run against focused upstream assertions (#656). |
| [RELEASING.md](RELEASING.md) | Beta/pre-release checklist and publish verification workflow. |
| [../CHANGELOG.md](../CHANGELOG.md) | Version history and user-visible changes. |
| [releases/README.md](releases/README.md) | Release-record convention, canonical filenames, and per-version evidence layout. |
| [releases/0.7.0/RELEASE_NOTES.md](releases/0.7.0/RELEASE_NOTES.md) | 0.7.0 release-note draft, user-facing scope, quality evidence, and known limits. |
| [releases/0.7.0/CANDIDATE_EVIDENCE.md](releases/0.7.0/CANDIDATE_EVIDENCE.md) | 0.7.0 package build, clean install smoke, and pre-tag checklist evidence. |
| [releases/0.7.0/DOCUMENTATION_AUDIT.md](releases/0.7.0/DOCUMENTATION_AUDIT.md) | 0.7.0 docs audit against live CLI help, config schema, fixtures, and generated output. |
| [releases/0.7.0/TEST_EVIDENCE.md](releases/0.7.0/TEST_EVIDENCE.md) | Release-facing claim-to-evidence inventory for 0.7.0. |
| [releases/0.7.0/PERFORMANCE_BASELINE.md](releases/0.7.0/PERFORMANCE_BASELINE.md) | Local translation, Spring smoke, and corpus reporting performance baseline for 0.7.0. |
| [releases/0.7.0/DIAGNOSTICS_TODO_AUDIT.md](releases/0.7.0/DIAGNOSTICS_TODO_AUDIT.md) | Diagnostics and TODO wording audit for framework and platform boundaries. |
| [decisions/](decisions/) | ADRs `0001` through `0025`; consult [Architecture](ARCHITECTURE.md#key-design-decisions) before changing settled policy. |
| [decisions/AUDIT-2026-06-17.md](decisions/AUDIT-2026-06-17.md) | Latest dated maturity and gap audit snapshot. |
| [decisions/AUDIT-2026-06-15.md](decisions/AUDIT-2026-06-15.md) | Prior maturity and gap audit snapshot. |
| [decisions/AUDIT-2026-06-13.md](decisions/AUDIT-2026-06-13.md) | Earliest rule-layer breadth snapshot. |
