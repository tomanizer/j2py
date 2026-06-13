## Audit summary

Audit refresh performed against local `main` at **`589eadb`** on **2026-06-13** (final deterministic-rule-layer pass).

Full write-up: [`docs/decisions/AUDIT-2026-06-13.md`](docs/decisions/AUDIT-2026-06-13.md)

Ongoing professional-quality work (P0–P3 buckets) is tracked in **#134**.

### Current state

- `make check` passes: ruff, strict mypy, **396** pytest passes (16 deselected).
- **`FUTURE_TARGETS` is empty** — all 10 curated construct fixtures graduated.
- `make test-targets` **succeeds** when no future xfail contracts remain (exit 0).
- `make corpus-spring-dense-check`: **100% average coverage**, 0 files with unhandled — baseline committed.
- `make corpus-spring-broad` (150 files): **99.71%** average coverage, **2** files with unhandled.

### Dense corpus (`make corpus-spring-dense-check`)

| Metric | Baseline → Current |
|--------|-------------------|
| Average coverage | **100.00%** → **100.00%** |
| Full-coverage files | 43 → **43** |
| Files with unhandled | 0 → **0** |

### Broad corpus (`make corpus-spring-broad`)

| Metric | Value |
|--------|-------|
| Average coverage | 99.71% |
| Full-coverage files | 92 / 94 |
| Files with unhandled | 2 |
| Parse / syntax success | 100% / 99.33% |

Remaining unhandled reasons (150-file sample):

```text
switch expression without default: 1
equals invocation with unexpected argument count: 1
```

## Findings

Since the initial 2026-06-13 snapshot (`d01061d`), #87 landed (#98), P0 fixes (#108–#111), static imports (#143), and import tracking (#146) improved broad-corpus signal. The rule layer is no longer blocked by construct xfails or the ambiguous-`get(...)` gap.

**This meta-issue's deterministic-translator scope is complete.** Remaining rule-layer gaps are tracked as focused issues under #134:

- **#88** — overload dispatch (dominant gap on 450-file sample)
- P3 one-offs — switch-without-default, `equals` arity

## Subtasks (original wave — complete)

- [x] #40 — corpus cleanup
- [x] #39 — sized array creation
- [x] #46 — method references and collection constructors
- [x] #42 — field default values
- [x] #41 — try-with-resources
- [x] #43 — static initializer and synchronized blocks
- [x] #44 — overload merge (constructors/builders)
- [x] #45 — corpus metrics refresh

## Subtasks (construct graduation wave — complete)

- [x] #72 — `var` keyword
- [x] #73 — switch fall-through
- [x] #74 — anonymous class fields
- [x] #75 / #92 / #93 — advanced streams

## Hygiene (complete)

- [x] Dense corpus baseline committed at 100% average coverage
- [x] `make test-targets` succeeds with empty `FUTURE_TARGETS`
- [x] #87 — ambiguous `get(...)` receiver typing

## Handoff

- [ ] **#88** — reprioritized under #131 / #134 (not a blocker for closing this umbrella)
- [x] Audit doc refreshed at `589eadb`
- [ ] Close this issue; use **#134** for P0–P3 tracking going forward

## Verification evidence

```bash
make check                      # 396 passed
make test-targets               # 0 selected, exit 0
make corpus-spring-dense-check  # no regressions, 100% avg
make corpus-spring-broad        # 99.71% avg, 2 unhandled files
```

## Done when

- [x] #87 completed
- [x] #88 reprioritized under #134 (#131 P1 bucket) with rationale
- [x] Dense corpus baseline committed
- [x] Final audit doc link updated
- [ ] Issue closed after merge of final audit refresh PR
