# Translation targets

Translation targets are the rule-layer backlog and regression contract for Java constructs.
They sit between assessment, corpus measurement, and normal fixture tests:

```text
doctor/corpus/harvest -> target contract -> rule implementation -> fixture regression
```

Use this document when a Java construct is important enough to track, but the deterministic
translator either cannot handle it yet or recently learned how to handle it and must not
regress.

This is about Java-to-Python source translation. It is separate from:

- [Assessment](DOCTOR.md), which diagnoses a project with `j2py doctor`;
- [Configuration](CONFIGURATION.md), which records project policy;
- [Framework plugins](FRAMEWORK_PLUGINS.md), which extract framework metadata;
- [Wiring](WIRING.md), which generates target-stack app assembly from sidecars.

## What targets are for

Targets make unsupported or newly supported Java constructs executable and reviewable:

| Situation | Use |
|---|---|
| A construct now translates deterministically | Graduated target or normal Java/Python fixture. |
| A construct is unsupported but should be implemented later | Strict future xfail target. |
| A corpus run finds a small reproducible gap | Reduce it to a target fixture. |
| LLM harvest finds a deterministic repair candidate | Promote it to a target or normal fixture. |
| A rule change needs regression coverage | Add or graduate a target before merging. |

The goal is to avoid vague backlog notes. A target should show the Java input, the Python
shape we expect, the fragments we forbid, and the issue or corpus source that explains why
the work matters.

## Test commands

Normal supported behavior runs in `make check`:

```bash
make check
```

Future roadmap targets run separately:

```bash
make test-targets
```

`make check` excludes the `target_translation` marker. `make test-targets` runs only strict
future xfail contracts. If there are no future targets, that empty state must be intentional
while no deferred concrete construct gap has been selected; it should not happen because we
forgot to register known gaps.

## The four lanes

### 1. Normal fixture suite

Normal fixtures live under:

```text
tests/fixtures/java/
tests/fixtures/python/
```

Use these for behavior that is fully supported and has exact expected output. Most rule
work should end here.

### 2. Graduated targets

Graduated targets live under:

```text
tests/fixtures/java/targets/
```

They are Java fixtures that were once roadmap examples or corpus-derived probes and now
translate deterministically. They run in `make check` through
`tests/targets/test_translation_targets.py`.

The bar is intentionally high:

- Java parses without errors;
- generated Python parses with `ast.parse`;
- rule coverage is `1.0`;
- no unhandled diagnostics remain;
- generated output contains no unsupported TODOs or `__j2py_todo__`.

Corpus-derived fast regressions that should not change committed corpus baselines also
belong here.

### 3. Graduated corpus constructs

Graduated corpus constructs live under:

```text
tests/fixtures/corpus/constructs/
```

These are tiny construct fixtures used by corpus presets with `--include-constructs`.
Because they participate in committed corpus baselines, do not put deferred xfail gaps in
this directory. Deferred gaps belong in `tests/fixtures/java/targets/` plus
`FUTURE_TARGETS`.

Current graduated construct coverage includes fixtures such as `AdvancedEnum`,
`AdvancedStreams`, `AnonymousAndInner`, `ComplexRecords`, `EnumConstantClassBody`,
`InterfaceDefaults`, `SealedClasses`, `SuperMethodCalls`, `SwitchFallthrough`,
`TextBlocks`, and `VarKeyword`.

### 4. Future targets

Future targets are strict `xfail` contracts registered in `FUTURE_TARGETS` inside:

```text
tests/targets/test_translation_targets.py
```

They are for unsupported behavior that should become deterministic next. A future target is
not just a failing file. It is a small contract with:

- a valid Java fixture;
- a tracking reference;
- a clear reason;
- expected Python fragments, forbidden fragments, or both;
- a strict xfail marker.

When the target unexpectedly passes, pytest reports it as a strict xfail failure. That is
the signal to graduate the behavior instead of leaving stale backlog behind.

## Current target state

Current corpus-derived fast target promotions:

| Fixture | Tracking | Rule-layer support |
|---|---|---|
| `tests/fixtures/java/targets/CorpusArrayTypeMapProbe.java` | `issue-252` | Array type class literals as map keys, promoted from Spring `PropertyEditorRegistrySupport.java`. |
| `tests/fixtures/java/targets/CorpusAssertStatementProbe.java` | `issue-252` | Java `assert_statement`, promoted from Commons Lang `CachedRandomBits.java`. |
| `tests/fixtures/java/targets/CorpusMalformedTernaryProbe.java` | `issue-252` | Jackson `InetSocketAddressSerializer.java` nested ternary/string-concat pattern. |
| `tests/fixtures/java/targets/IteratorPostIncrementSubscript.java` | `issue-252/jackson-arrayiterator-invalid-python-output` | Post-increment expressions used inside array subscripts split into a value read plus a following increment, preserving old-index semantics. |

Current future target backlog:

| Fixture | Tracking | Missing rule-layer support |
|---|---|---|
| _(none)_ | _(none)_ | This empty future-target backlog is intentional while no deferred concrete construct gap has been selected; add a strict `TranslationTarget` when the next unsupported target is identified. |

Current graduated harvest fixtures:

| Fixture | Tracking | Rule-layer support |
|---|---|---|
| `tests/fixtures/llm/MultiDimArray.java` | `issue-308` | `new int[rows][cols]` -> `[[0] * cols for _ in range(rows)]` |

Harvest-only mypy-repair cases, such as interface defaults or overload dispatch repair,
stay in `.j2py/harvest/records.jsonl` until the contract includes a mypy bar or a
deterministic fixture pair is added. See [LLM harvest](LLM_HARVEST.md).

## Adding a future target

Add a future target when all of these are true:

- the construct is concrete and reproducible;
- it is not worth fixing in the same change;
- the desired Python shape is clear enough to test;
- the target belongs to a pattern family worth tracking.

Steps:

1. Add a small Java fixture under `tests/fixtures/java/targets/`.
2. Add a strict `TranslationTarget` entry to `FUTURE_TARGETS`.
3. Include `tracking`, `reason`, `expected_fragments`, and `forbidden_fragments` where
   useful.
4. Run `make test-targets` and confirm the target is an expected xfail.
5. File or reference a GitHub issue for the pattern family, not just the single fixture.

Template:

```python
TranslationTarget(
    fixture="ExampleGap.java",
    fixture_root=TARGET_FIXTURES,
    tracking="issue-123",
    reason="Example construct is not fully supported",
    expected_fragments=("expected_python_fragment()",),
    forbidden_fragments=("__j2py_todo__",),
)
```

## Graduating a target

When implementing a translation rule:

1. Run `make test-targets` and identify the affected future target.
2. Implement the smallest deterministic rule that makes the target pass.
3. Add or update the normal Java/Python fixture pair when exact output matters.
4. Remove the target from `FUTURE_TARGETS`.
5. Keep the Java fixture under `tests/fixtures/java/targets/` if it is useful as a
   graduated target, or delete it if normal fixtures fully cover the behavior.
6. Run `make check` and `make test-targets`.
7. For corpus-derived gaps, run the relevant corpus check from
   [Corpus scoreboard](CORPUS_SCOREBOARD.md).

Do not leave a passing target as xfail. Strict xfail is there to force cleanup.

## From doctor, corpus, or harvest to target

### From doctor

`j2py doctor` reports unhandled diagnostics, semantic warnings, unresolved imports, and
low-coverage files. Use those signals to identify construct families, then reduce one
representative file to a small target fixture.

Do not copy a whole application class into targets when a smaller construct fixture would
prove the same rule.

### From corpus

Corpus presets reveal broad regression patterns across real libraries. When a corpus gap is
small and reproducible, reduce it to `tests/fixtures/java/targets/` so `make check` or
`make test-targets` catches it quickly without rerunning a dense corpus.

### From LLM harvest

LLM harvest can suggest deterministic repair candidates. `make harvest-suggest-targets`
drafts `FUTURE_TARGETS` snippets, but it does not merge them automatically. A contributor
must review the snippet, reduce the case if needed, and add the target by hand.

GitHub issues for harvested gaps can be drafted or filed via:

```bash
make harvest-promote-dry
make harvest-promote-issues
```

See [LLM harvest](LLM_HARVEST.md), especially the promotion workflow.

## Good target hygiene

A good target is:

- small enough to understand without the original corpus file;
- valid Java;
- focused on one construct family;
- explicit about expected and forbidden Python fragments;
- linked to an issue, corpus source, or harvest record;
- graduated promptly when implemented.

Avoid:

- broad application fixtures that mix many unrelated gaps;
- future targets without expected or forbidden fragments;
- xfail entries with vague reasons;
- using target fixtures as a substitute for exact Java/Python fixture pairs;
- adding deferred gaps to `tests/fixtures/corpus/constructs/`, because that changes corpus
  baseline semantics.

## Related docs

- [Assessment](DOCTOR.md) explains project readiness scans with `j2py doctor`.
- [Corpus scoreboard](CORPUS_SCOREBOARD.md) explains dense preset metrics and baselines.
- [LLM harvest](LLM_HARVEST.md) explains harvest triage and target suggestion drafts.
- [Equivalence testing](EQUIVALENCE_TESTING.md) explains behavior-oriented verification.
- [Architecture](ARCHITECTURE.md) explains where fixture and target tests fit in the
  quality model.
