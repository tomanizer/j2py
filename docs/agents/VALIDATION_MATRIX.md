# Validation Matrix

Pick the smallest gate that proves the changed behavior. Add broader gates for broader
blast radius.

## Default Gates

| Situation | Gate |
|-----------|------|
| Normal code change | `make check` |
| PR-ready local gate | `make ci-local-pr` |
| Release/package readiness | `make release-check` |
| Unsure | [developer/VALIDATION_GATES.md](../developer/VALIDATION_GATES.md) |

## Focused Gates

| Change | Command |
|--------|---------|
| Parser/analyzer | `pytest tests/parse tests/analyze -q` |
| Translation rules | `pytest tests/translate -q` |
| Fixture equality | `pytest tests/translate/skeleton/test_fixtures.py -q` |
| Runtime helpers | `pytest tests/translate/test_runtime_dispatch.py -q` |
| Platform/JDK boundaries | `pytest tests/translate/test_platform_imports.py tests/translate/test_runtime_dispatch.py -q` |
| Config | `pytest tests/config tests/translate/skeleton/test_config.py tests/cli/test_main.py -q` |
| CLI/API | `pytest tests/cli/test_main.py tests/test_pipeline.py -q` |
| Validation | `pytest tests/validate -q` |
| Doctor/SARIF | `pytest tests/test_doctor.py tests/test_sarif.py -q` |
| Reports/dashboards | `pytest tests/test_report.py tests/test_state_dashboard.py tests/cli/test_main.py -q` |
| Wiring | `pytest tests/wire -q` |
| LLM provider code | `pytest tests/llm tests/cli/test_main.py -q` |
| Packaging | `pytest tests/packaging -q` |
| Docs links and anchors | `pytest tests/test_docs_links.py -q` |
| Release-doc inventory | `pytest tests/test_release_coverage_inventory.py tests/test_release_candidate_checklist.py tests/test_release_diagnostics_todo_audit.py tests/test_release_performance_baseline.py tests/packaging/test_check_sdist_hygiene.py -q` |

## Semantic Gates

| Gate | Proves |
|------|--------|
| `make test-equivalence` | Literal-oracle equivalence fixtures; no JDK or LLM. |
| `make equivalence-report` | Equivalence report and verified-surface context. |
| `make test-behavior` | Java/Python process behavior; requires JDK. |
| `make test-targets` | Future strict-xfail translation targets. |
| `make test-spring-smoke` | Spring translate -> sidecar -> `j2py-wire` -> FastAPI smoke path. |

## Corpus Gates

| Gate | Use for |
|------|---------|
| `make corpus-hotspots` | Cross-corpus gap ranking from committed baselines. |
| `make corpus-commons-lang-dense-check` | Apache Commons Lang patterns. |
| `make corpus-guava-dense-check` | Guava collections/generics/utilities. |
| `make corpus-jackson-dense-check` | Jackson databind-style code. |
| `make corpus-caffeine-dense-check` | Caffeine cache/generic code. |
| `make corpus-spring-dense-check` | Spring Framework source constructs. |
| `make corpus-petclinic-dense-check` | Spring PetClinic application slice. |

In worktrees, set `J2PY_CORPUS_ROOT` to the main checkout if corpus clones live there.

## Live Or Network Gates

Run only when explicitly requested or necessary:

| Gate | Requirement |
|------|-------------|
| `make test-llm-e2e` | `ANTHROPIC_API_KEY`; live provider call. |
| `make test-llm-gemini-e2e` | `GEMINI_API_KEY`; live provider call. |
| `npm ci` in `packages/j2py-vscode` | Network unless cached. |
| `npm run package` in `packages/j2py-vscode` | VSIX package smoke. |

If not run, say so.

## Evidence Rules

- Focused tests prove only their covered behavior.
- `make check` does not prove live LLM, JDK behavior, VSIX packaging, or corpus health.
- Corpus checks prove baseline regression status, not enterprise runtime support.
- Release-doc tests prove inventory/link consistency, not current release readiness.
- Missing optional tools, credentials, JDK, network, or sandbox access are validation
  limits; report them.

## Final Evidence

Final response should name:

- changed files/subsystems;
- validation commands and results;
- skipped relevant gates;
- commit/push/PR status when requested;
- dirty files if any remain.
