# Translation Target Tests

The normal fixture suite records behavior that j2py already supports as exact Java to
Python fixture pairs. The target suite records roadmap examples and graduated roadmap
fixtures that should keep translating cleanly.

Graduated target fixtures run in `make check`. Only future `xfail` contracts use the
`target_translation` marker and run via `make test-targets`.

Run the normal gate:

```bash
make check
```

Run future roadmap xfail targets:

```bash
make test-targets
```

The suite has three lanes:

- **Graduated targets**: Java fixtures under `tests/fixtures/java/targets/` that now
  translate deterministically. These run in `make check`, must parse, produce valid
  Python, reach `coverage == 1.0`, and report no unhandled diagnostics.
- **Graduated corpus constructs**: Java fixtures under
  `tests/fixtures/corpus/constructs/` that reach the same bar as graduated targets
  (`AdvancedEnum`, `AdvancedStreams`, `AnonymousAndInner`, `ComplexRecords`,
  `EnumConstantClassBody`, `InterfaceDefaults`, `SealedClasses`, `SuperMethodCalls`,
  `SwitchFallthrough`, `TextBlocks`, `VarKeyword`). These also run in `make check`.
- **Future targets**: strict `xfail` contracts in `FUTURE_TARGETS` for unsupported
  behavior that should become supported next. Promoted from LLM harvest triage where
  the rule layer leaves explicit failure markers (`coverage < 1.0`).

`FUTURE_TARGETS` is populated manually. There is no automation that turns GitHub issues,
corpus hotspot rows, audit findings, or harvest records into future targets. The person
or agent triaging a concrete unsupported Java construct owns one of two outcomes:

- fix the gap immediately and add normal regression coverage, or
- defer it by adding a strict `TranslationTarget` xfail before leaving the gap as backlog.

When a new construct gap is identified and deferred, add a fixture here and register it in
`FUTURE_TARGETS` before implementing the rule later.

Current future corpus-construct backlog:

| Fixture | Tracking | Rule-layer gap |
|---|---|---|
| `tests/fixtures/llm/AssertProbe.java` | `llm-harvest-assert` | `assert_statement` → `# TODO(j2py): unsupported` |
| `tests/fixtures/llm/MultiDimArray.java` | `llm-harvest-multi-dim-array` | `new int[rows][cols]` → `__j2py_todo__` |

Harvest-only mypy-repair cases (e.g. `InterfaceDefaults`, overload dispatch) stay in
`.j2py/harvest/records.jsonl` until the target contract includes a mypy bar or a
deterministic fixture pair is added. See [LLM_HARVEST.md](LLM_HARVEST.md).

Each future target case has:

- a Java fixture under `tests/fixtures/java/targets/` or
  `tests/fixtures/corpus/constructs/`
- expected Python fragments that describe the future translation contract
- forbidden fragments such as unsupported TODOs
- a strict `xfail` marker explaining the missing translator capability
- a tracking reference to the issue, corpus gap, or roadmap slice that will implement it

When implementing a translation rule:

1. Run `make test-targets` and identify the future or graduated target affected by the
   change.
2. Implement the smallest deterministic rule that makes that target pass.
3. Move or copy the now-supported behavior into the normal fixture suite under
   `tests/fixtures/java/` and `tests/fixtures/python/`.
4. Move the target from `FUTURE_TARGETS` into the graduated fixture check, or delete it
   if the normal fixture fully covers it.
5. Run `make check` and `make test-targets`. For rule-layer changes, also run relevant
   corpus baseline checks (see [docs/CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md)).

This gives us two signals:

- `make check`: supported behavior and graduated roadmap fixtures must stay green.
- `make test-targets`: future xfail targets alert us when missing behavior unexpectedly
  starts passing.
