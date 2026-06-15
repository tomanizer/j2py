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
  `CorpusArrayTypeMapProbe`, `CorpusAssertStatementProbe`,
  `CorpusMalformedTernaryProbe`, `EnumConstantClassBody`, `InterfaceDefaults`,
  `SealedClasses`, `SuperMethodCalls`, `SwitchFallthrough`, `TextBlocks`, `VarKeyword`).
  These also run in `make check`.
- **Graduated harvest fixtures**: selected Java fixtures under `tests/fixtures/llm/`
  that were promoted out of future targets and now translate deterministically
  (`MultiDimArray`). These run in `make check`.
- **Future targets**: strict `xfail` contracts in `FUTURE_TARGETS` for unsupported
  behavior that should become supported next. Promoted from LLM harvest triage where
  the rule layer leaves explicit failure markers (`coverage < 1.0`).

`FUTURE_TARGETS` is populated manually. There is no automation that turns harvest records
directly into `FUTURE_TARGETS` entries — an agent or contributor still merges snippets
from `make harvest-suggest-targets` or adds fixtures by hand. **GitHub issues** for
pattern families can be drafted or filed via `make harvest-promote-dry` /
`make harvest-promote-issues` (see [LLM_HARVEST.md](LLM_HARVEST.md)). The person or agent
triaging a concrete unsupported Java construct owns one of two outcomes:

- fix the gap immediately and add normal regression coverage, or
- defer it by adding a strict `TranslationTarget` xfail before leaving the gap as backlog.

When a new construct gap is identified and deferred, add a fixture here and register it in
`FUTURE_TARGETS` before implementing the rule later. File the GitHub issue as a
**pattern family**, not a single-fixture fix — see
[LLM_HARVEST.md — Promoting harvest → GitHub issues](LLM_HARVEST.md#promoting-harvest--github-issues-pattern-families).

Current future corpus-construct backlog:

| Fixture | Tracking | Missing rule-layer support |
|---|---|---|
| `tests/fixtures/corpus/constructs/IteratorPostIncrementSubscript.java` | `issue-252/jackson-arrayiterator-invalid-python-output` | Split Java post-increment expressions used inside array subscripts into a value read plus a following increment so generated Python parses and preserves old-index semantics. |
| `tests/fixtures/corpus/constructs/StaticImportEnumConstants.java` | `issue-252/guava-elementtype-static-imports` | Resolve `java.lang.annotation.ElementType` static enum imports used in annotations instead of surfacing unknown static-import TODOs. |

Current graduated harvest fixtures:

| Fixture | Tracking | Rule-layer support |
|---|---|---|
| `tests/fixtures/llm/MultiDimArray.java` | `issue-308` | `new int[rows][cols]` → `[[0] * cols for _ in range(rows)]` |

Harvest-only mypy-repair cases (e.g. `InterfaceDefaults`, overload dispatch) stay in
`.j2py/harvest/records.jsonl` until the target contract includes a mypy bar or a
deterministic fixture pair is added. See [LLM_HARVEST.md](LLM_HARVEST.md).

Each future target case has:

- a Java fixture under `tests/fixtures/java/targets/` or
  `tests/fixtures/corpus/constructs/`, or a selected harvest fixture under
  `tests/fixtures/llm/`
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
