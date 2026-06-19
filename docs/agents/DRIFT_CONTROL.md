# Drift Control

Use before adding code, docs, commands, files, helpers, processes, or tests.

## Rule

Do not create a new thing until you have checked whether the repo already has one.

## Required Evidence

Before adding a new helper, module, command, doc, workflow, fixture family, or test
harness, collect enough evidence to answer:

- What existing owner module or doc owns this behavior?
- What existing helper, fixture, command, or process is closest?
- Why is extending it insufficient?
- Which validation gate proves the change did not fork behavior?

If you cannot answer those, stop and search more.

## Search First

Before adding a name or concept:

```bash
rg -n "name_or_concept" .
rg --files | rg "path_or_filename"
```

For code behavior:

```bash
rg -n "helper_or_behavior" j2py tests
```

For docs or process behavior:

```bash
rg -n "workflow_or_phrase" README.md CONTRIBUTING.md AGENTS.md CLAUDE.md docs
```

## Reuse Order

Prefer:

1. existing public API or CLI behavior;
2. existing owner module;
3. existing helper;
4. existing test harness or fixture pattern;
5. existing doc section;
6. small extension to an existing pattern.

Create a new module, helper, command, doc, or process only when the existing owner cannot
reasonably contain the behavior.

## Stop Conditions

Stop before editing if any of these are true:

- two files already implement similar behavior;
- an existing command or Make target already covers the workflow;
- a doc page already explains the concept in another section;
- the new abstraction has only one caller and no established local pattern;
- the change crosses core translation, framework plugins, wiring, and user docs without a
  clear owner boundary.

In those cases, extend or consolidate the existing owner first. If a new owner is still
needed, state why in the issue, PR, or final report.

## Duplication Checks

| Adding | Check first |
|--------|-------------|
| helper function | `j2py/translate/rules/`, owner module, runtime helpers |
| translation rule | owning `class_*`, `stmt_*`, `expr_*`, stream, or rules module |
| runtime shim | `j2py/translate/runtime/j2py_runtime.py` |
| CLI option | `j2py/cli/`, [CLI](../CLI.md), CLI tests |
| config field | `j2py/config/`, [Configuration](../CONFIGURATION.md), config tests |
| diagnostic | [Diagnostics](../developer/DIAGNOSTICS.md), doctor/SARIF/report tests |
| wiring behavior | `j2py/wire/targets/`, `j2py/wire/validation.py`, wiring tests |
| framework behavior | framework plugin docs, sidecar schema, Spring docs if applicable |
| doc page | [docs/README.md](../README.md), nearby docs |
| process rule | `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `docs/agents/`, `docs/developer/` |

## Process Ownership

Do not invent a second workflow:

- developer validation -> [Validation gates](../developer/VALIDATION_GATES.md);
- agent routing -> [Coding Agent Guides](README.md);
- release evidence -> repo hygiene docs;
- user workflow -> User Docs;
- framework-specific workflow -> Java Enterprise Framework Guides.

## Final Drift Check

- Search for duplicate names or near-duplicate phrases.
- Link new docs from one owning index, not every index.
- Link root entry points to indexes unless a deep page is a true start page.
- Reuse existing fixtures and harnesses where possible.
- Explain any new abstraction or process if it was necessary.
- Report the owner you extended and the validation gate you used.
