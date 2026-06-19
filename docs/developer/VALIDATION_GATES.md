# Validation Gates

Use this guide to choose the right local gate. `make check` is the normal default, but
some changes need narrower or stronger evidence.

## Default Gates

| Command | What it proves | Use when |
|---------|----------------|----------|
| `make check` | Ruff format/lint, mypy, normal pytest suite without behavior/live LLM/target xfail tests. | Most code and docs changes before commit. |
| `make ci-local-pr` | Local approximation of required PR CI, including Python 3.11 test leg and equivalence floor. | Before pushing a normal PR. |
| `make ci-local-pr-full` | Local PR gate plus Python 3.12 leg. | Before larger PRs or compatibility-sensitive changes. |
| `make release-check` | Release tests plus package build and distribution checks. | Release or packaging changes. |

## Focused Gates

| Change | Command |
|--------|---------|
| Parser/analyzer | `pytest tests/parse tests/analyze -q` |
| Translation rules | `pytest tests/translate -q` |
| Config behavior | `pytest tests/config tests/translate/skeleton/test_config.py tests/cli/test_main.py -q` |
| CLI/API behavior | `pytest tests/cli/test_main.py tests/test_pipeline.py -q` |
| Validation output | `pytest tests/validate -q` |
| Doctor/SARIF | `pytest tests/test_doctor.py tests/test_sarif.py -q` |
| Wiring targets | `pytest tests/wire -q` |
| LLM providers | `pytest tests/llm tests/cli/test_main.py -q` |
| Packaging metadata | `pytest tests/packaging -q` |
| Docs release inventory | `pytest tests/test_release_coverage_inventory.py tests/test_release_candidate_checklist.py tests/test_release_diagnostics_todo_audit.py -q` |

## Semantic Gates

| Command | What it proves |
|---------|----------------|
| `make test-equivalence` | Literal-oracle differential tests for translated fixtures; no JDK or LLM required. |
| `make equivalence-report` | Equivalence gate plus verified-surface report and floor check context. |
| `make test-behavior` | Java/Python stdout/stderr/exit-code behavior tests; requires a local JDK. |
| `make test-targets` | Future translation roadmap xfail contracts. |
| `make test-spring-smoke` | Optional Spring PetClinic translate -> sidecar -> wire -> FastAPI smoke path. |

Use semantic gates when a change affects runtime behavior, JDK lowering, framework smoke
coverage, or a behavior already represented in equivalence fixtures.

## Corpus Gates

Corpus gates compare translated output against committed dense baselines or produce
hotspot reports. They are useful when a change can affect many real Java files.

| Command | Use when |
|---------|----------|
| `make corpus-hotspots` | Ranking cross-corpus unhandled/syntax gaps from committed baselines. |
| `make corpus-commons-lang-dense-check` | Rule changes affecting Apache Commons Lang-like utility code. |
| `make corpus-guava-dense-check` | Collection, generic, optional, and utility patterns. |
| `make corpus-jackson-dense-check` | Annotation-heavy and serialization-shaped code. |
| `make corpus-caffeine-dense-check` | Complex generic/cache code. |
| `make corpus-spring-dense-check` | Spring framework construct coverage. |
| `make corpus-petclinic-dense-check` | Spring application-style coverage. |

In worktrees, set `J2PY_CORPUS_ROOT` to the main checkout if corpus clones live there.
Do not update baselines unless the diff has been reviewed as intentional.

## Live And Optional Gates

Live LLM gates are excluded from normal CI and must be run only when explicitly requested:

```bash
make test-llm-e2e
make test-llm-gemini-e2e
```

VS Code extension gates run from `packages/j2py-vscode`:

```bash
npm ci
npm run compile
npm run package
```

`npm ci` may need network access. Do not treat a skipped VSIX package as proof that the
extension works; record it as not run.

## Review Checklist

- The chosen gate matches the changed subsystem.
- Broad changes run `make check` or a stronger PR gate.
- Corpus baselines are not updated casually.
- Live LLM and VS Code package gates are reported honestly when not run.
