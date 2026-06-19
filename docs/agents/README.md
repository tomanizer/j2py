# Coding Agent Guides

Agent-native routing for repo changes. Use this before editing.

## Order

1. Classify the task in [CHANGE_ROUTING.md](CHANGE_ROUTING.md).
2. Run the drift check in [DRIFT_CONTROL.md](DRIFT_CONTROL.md).
3. Pick the gate in [VALIDATION_MATRIX.md](VALIDATION_MATRIX.md).
4. Check doc ownership in [DOCS_MAP.md](DOCS_MAP.md).
5. Check failure patterns in [COMMON_FAILURES.md](COMMON_FAILURES.md).

Human docs remain authoritative for detail:

- [Developer Docs](../README.md#developer-docs)
- [docs/developer](../developer/README.md)
- [Architecture](../ARCHITECTURE.md)
- [ADRs](../decisions/)

## Non-Negotiables

- Preserve Java-to-Python reviewability: same class/method/control-flow shape where possible.
- Prefer deterministic rule-layer fixes over LLM prompt changes for translatable Java constructs.
- No live LLM calls in normal tests, `make check`, or CI.
- Do not update corpus baselines without reviewed no-regression evidence.
- Do not use release notes, case studies, or audits as current command references.
- Keep framework runtime behavior out of core translation.
- Preserve unrelated user changes.
- Search before creating helpers, docs, commands, files, tests, or process rules.

## Fast Routes

| Task | Route | Validate |
|------|-------|----------|
| Java construct rule | [Java construct rule](CHANGE_ROUTING.md#java-construct-rule) | `pytest tests/translate -q`; usually `make check` |
| Parser/analyzer | [Parser or analyzer change](CHANGE_ROUTING.md#parser-or-analyzer-change) | `pytest tests/parse tests/analyze -q` |
| Equivalence/behavior | [Equivalence or behavior coverage](CHANGE_ROUTING.md#equivalence-or-behavior-coverage) | `make test-equivalence`; `make test-behavior` when JDK behavior changes |
| Framework plugin | [Framework plugin change](CHANGE_ROUTING.md#framework-plugin-change) | plugin + sidecar tests |
| Wiring target | [Wiring target change](CHANGE_ROUTING.md#wiring-target-change) | `pytest tests/wire -q` |
| Doctor/SARIF/diagnostics | [Diagnostics doctor or SARIF change](CHANGE_ROUTING.md#diagnostics-doctor-or-sarif-change) | `pytest tests/test_doctor.py tests/test_sarif.py -q` |
| LLM provider/prompt | [LLM provider or prompt change](CHANGE_ROUTING.md#llm-provider-or-prompt-change) | `pytest tests/llm tests/cli/test_main.py -q` |
| CLI/API | [CLI or public API change](CHANGE_ROUTING.md#cli-or-public-api-change) | `pytest tests/cli/test_main.py tests/test_pipeline.py -q` |
| Docs | [Documentation change](CHANGE_ROUTING.md#documentation-change) | Markdown link check + release-doc tests |
| Root docs | [Root entrypoint change](CHANGE_ROUTING.md#root-entrypoint-change) | Markdown link check + `cmp -s AGENTS.md CLAUDE.md` |
| Packaging/release | [Packaging or release workflow change](CHANGE_ROUTING.md#packaging-or-release-workflow-change) | `pytest tests/packaging -q`; `make release-check` for release readiness |

## Before Final

- `git status --short` reviewed.
- Only relevant files staged or reported.
- Validation commands and results recorded.
- Skipped live/network/JDK gates called out.
- Markdown links checked after docs/heading/filename changes.
- `AGENTS.md` and `CLAUDE.md` compared if either changed.
- Drift check completed before adding new helpers, docs, commands, files, tests, or process rules.
- Issue/PR/commit/push requests actually completed before claiming completion.
