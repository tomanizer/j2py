# Case study — translating java-semver (jsemver) end-to-end

Status: **Active** (issue [#613](https://github.com/tomanizer/j2py/issues/613),
P0.1, defining-risk finding from [AUDIT-2026-06-17](decisions/AUDIT-2026-06-17.md)).

This is the **first external** end-to-end conversion case study. Every prior quality
signal — corpus node coverage, the equivalence surface — traces back to curated j2py
fixtures or pinned corpora sampled for the scoreboard. Here we take a third-party OSS
library off the shelf, translate it with the rule layer, link it, and run **its own**
JUnit suite (ported to pytest) against the Python output. The point is to replace
*asserted* library-scale equivalence with *demonstrated* equivalence, and to publish the
residual gap list honestly.

## The subject

[java-semver](https://github.com/zafarkhaja/jsemver) (`com.github.zafarkhaja.semver`),
tag `v0.10.2`, commit `75b5abe97ca55c4569ea84e09330db22a0df2db7`, MIT license. A pure
Semantic-Versioning parsing and comparison library: ~4.9k LOC of main source across 26
files, zero runtime dependencies, ~3k LOC of JUnit 5 tests. It was the recommended first
trial in #613 because it is small, dependency-free, and exhaustively tested.

The whole library is pinned as the `jsemver` corpus preset
([`scripts/corpus/corpus_presets.py`](../scripts/corpus/corpus_presets.py)) for
scoreboard / hotspot work over the full tree. For the hermetic in-`make check` loop, the
`com.github.zafarkhaja.semver.util` package (`Stream` + `UnexpectedElementException`) is
vendored under
[`tests/fixtures/case_study/jsemver/java/`](../tests/fixtures/case_study/jsemver/java)
(MIT, headers intact).

## What the rule layer produced (whole tree)

Rule layer only, no LLM (`j2py translate src/main/java --no-llm`):

| Metric | Result |
|---|---|
| Files translated | 26 / 26 |
| `ast.parse` clean | **26 / 26** |
| `# TODO(j2py)` markers emitted | **0** |
| Node coverage | ~100% on every file |

The headline restated: **the deterministic rule layer reaches every node of a real,
never-before-seen external library, emits zero "I-couldn't-translate-this" markers, and
every file is syntactically valid Python.** Mechanically, the translator handles this
library completely.

## The throughline: 100% node coverage ≠ runnable

Node coverage measures mechanical completion, not correctness — the same lesson as the
[`tuple` case study](CASE_STUDY_COMMONS_LANG_TUPLE.md), now confirmed on external code.
A static lint over the untouched output shows the gap immediately: **139 `F821`
undefined-name findings** across the tree. Most are harmless (type-only annotations under
`from __future__ import annotations`), but a systematic minority are real binding and
lowering defects: bare references to sibling static members (`lt`, `gte`, `eq`),
inner-class references (`Builder`, `Validators`, `Helper`), unqualified enum constants
(`DOT`, `HYPHEN`, `EOI`, `DIGIT`), and un-lowered JDK types (`Arrays`, `Optional`,
`Character`, `Predicate`).

## The closed loop: `util` package vs. its own `StreamTest`

To turn this from observation into a measured behavioural result, the `util` package is
run against the library's own `StreamTest` (14 cases) ported one-for-one to pytest in
[`tests/case_study/test_jsemver_case_study.py`](../tests/case_study/test_jsemver_case_study.py).
The translation, patching, and linking happen in
[`tests/case_study/jsemver_harness.py`](../tests/case_study/jsemver_harness.py).

| File | Node coverage | `# TODO(j2py)` | Confidence | Semantic warnings |
|---|---|---|---|---|
| `UnexpectedElementException` | 100% | 0 | 0.99 | 9 |
| `Stream` | 100% | 0 | 0.99 | 30 |

**Result: 14 / 14 ported `StreamTest` cases pass** against the rule-layer translation —
but only after **6 documented translator-defect patches** and **2 external-dependency
stubs**. The two kinds of intervention are kept strictly separate in the harness.

### External-dependency stubs (scaffolding, not under test)

These are JDK symbols the `util` package depends on but that are out of scope for the
translated logic — analogous to the dependency stubs in the `tuple` and equivalence
harnesses:

- `java.util.Arrays` — minimal `toString`.
- `java.lang.RuntimeException` base — Python `Exception` plus a `get_message()` shim for
  the `Throwable.getMessage()` the test calls.

### Residual translator defects (the failure list)

Each remaining entry is a real defect in the deterministic rule-layer output. The harness
applies one minimal, documented patch per gap so the loop can close; the gap inventory is
locked by `test_residual_gap_inventory`. **This list is the deliverable** — it is exactly
where the current rule layer emits Python that does not preserve the Java.

| Gap id | Module | Defect |
|---|---|---|
| `JSEMVER-1` | `UnexpectedElementException` | JDK builtin `RuntimeException` emitted as a sibling-package import (`from ...util.RuntimeException import RuntimeException`). |
| `JSEMVER-2` | `Stream` | Java array `.clone()` not lowered to a Python copy (`elements.clone()` → `AttributeError`). |
| `JSEMVER-5` | `Stream` | `java.util.Arrays.copyOfRange(...)` not lowered to a Python slice. |

`JSEMVER-6`, which emitted Java-style `next_`/`has_next` without Python `__iter__` /
`__next__` bridges on an anonymous `Iterator`, was removed from the residual list by the
deterministic iterator-protocol fix tracked in issue #643. `JSEMVER-3`, which emitted a
bare enclosing-field reference in an anonymous-class field initializer, was removed from
the residual list by the deterministic anonymous-capture fix tracked in issue #642.
`JSEMVER-4`, which had turned a constructor argument into control-flow (exception
chaining), was removed from the residual list by the deterministic throw-constructor fix
tracked in issue #641.

## Honest scope and conclusion

- **Demonstrated, not asserted:** an external OSS library's own test suite now runs
  against j2py output in-repo, hermetically, in `make check`.
- **Mechanical coverage is genuinely high:** 26/26 files parse, zero TODO markers — the
  rule layer is not bluffing about reach.
- **Correctness has a measured, enumerated gap:** 3 concrete translator defects still block a
  ~400-LOC, 14-test package from running as-translated. Extrapolated across the 139 `F821`
  findings on the full tree, the larger `Version` / `expr` / parser surface will surface
  more of the same categories (sibling static refs, inner-class binding, JDK lowering).

### Next steps (tracked under #613 follow-ups)

1. Promote the remaining three `JSEMVER-*` defects into deterministic rule-layer fixes with
   fixtures, then drop the corresponding harness patches.
2. Extend the closed loop to the `Version` value class (parse / compare / increment /
   `toString`) — the library's core and the bulk of `VersionTest`.
3. Add a `jsemver-baseline.json` corpus baseline once the tree is run through
   `translate_corpus.py` so the full-tree node-coverage number is regression-gated.
