# Case study — translating java-semver (jsemver) end-to-end

Status: **Complete** for the scoped end-to-end use case (issue
[#613](https://github.com/tomanizer/j2py/issues/613) plus Version-core extension
[#654](https://github.com/tomanizer/j2py/issues/654)); remaining full-tree corpus
baseline work is tracked separately.

This is the **first external** end-to-end conversion case study. Every prior quality
signal — corpus node coverage, the equivalence surface — traces back to curated j2py
fixtures or pinned corpora sampled for the scoreboard. Here we take a third-party OSS
library off the shelf, translate it with the rule layer, link it, and run ported slices
of **its own** JUnit suite against the Python output. The point is to replace
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
`com.github.zafarkhaja.semver.util` package (`Stream` + `UnexpectedElementException`)
and the `Version` / parser dependency closure are vendored under
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
A static lint over the untouched whole-tree output originally showed **139 `F821`
undefined-name findings**. The in-repo Version-core closure now links and runs its
exercised behavior, and a lint pass over the seven generated Version-core files reports
**0 `F821` findings**. The remaining full-tree work is outside this seven-file closed
loop and belongs with the corpus baseline follow-up.

## Closed loop 1: `util` package vs. its own `StreamTest`

To turn this from observation into a measured behavioural result, the `util` package is
run against the library's own `StreamTest` (14 cases) ported one-for-one to pytest in
[`tests/case_study/test_jsemver_case_study.py`](../tests/case_study/test_jsemver_case_study.py).
The translation, patching, and linking happen in
[`tests/case_study/jsemver_harness.py`](../tests/case_study/jsemver_harness.py).

| File | Node coverage | `# TODO(j2py)` | Confidence | Semantic warnings |
|---|---|---|---|---|
| `UnexpectedElementException` | 100% | 0 | 0.99 | 9 |
| `Stream` | 100% | 0 | 0.99 | 30 |

**Result: 14 / 14 ported `StreamTest` cases pass** against the rule-layer translation,
with **0 residual translator-defect patches**. External scaffolding remains separate from
translator-gap patches in the harness.

### External-dependency stubs (scaffolding, not under test)

These are JDK symbols the `util` package depends on but that are out of scope for the
translated logic — analogous to the dependency stubs in the `tuple` and equivalence
harnesses:

- `java.util.Arrays` — minimal `toString`.

### Residual translator defects (closed list)

The locked residual translator-defect list is now empty: the harness applies no
translator-gap patches for the `util` package before running the ported `StreamTest`
cases. `test_residual_gap_inventory` keeps that zero-patch state locked.

`JSEMVER-1`, which emitted Java `RuntimeException` as a same-package import instead of a
Python builtin exception base, was removed from the residual list by the deterministic
superclass-binding fix tracked in issue #644. `JSEMVER-6`, which emitted Java-style
`next_`/`has_next` without Python `__iter__` / `__next__` bridges on an anonymous
`Iterator`, was removed from the residual list by the deterministic iterator-protocol fix
tracked in issue #643. `JSEMVER-3`, which emitted a bare enclosing-field reference in an
anonymous-class field initializer, was removed from the residual list by the deterministic
anonymous-capture fix tracked in issue #642. `JSEMVER-4`, which had turned a constructor
argument into control-flow (exception chaining), was removed from the residual list by the
deterministic throw-constructor fix tracked in issue #641. `JSEMVER-2`, which emitted
Java array `.clone()` as a Python method call instead of a shallow list copy, was removed
from the residual list by the deterministic array-copy lowering fix tracked in issue
#645. `JSEMVER-5`, which emitted `java.util.Arrays.copyOfRange(...)` as an unresolved
helper call instead of a Python slice, was removed from the residual list by the
deterministic slice-lowering fix tracked in issue #646.

## Closed loop 2: `Version` core vs. the VersionTest slice

Issue [#654](https://github.com/tomanizer/j2py/issues/654) extends the hermetic loop to
the library core: `Version`, `VersionParser`, parser exceptions, `Parser`, and the shared
`Stream` utility. The harness links the seven-file dependency closure with shared
module-level class/static indexes, supplies only external JDK-style scaffolding
(`Optional` and `ExpressionParser`), and applies **0 residual translator-defect patches**.

| File | Node coverage | `# TODO(j2py)` | Semantic warnings |
|---|---:|---:|---:|
| `ParseException` | 100% | 0 | 5 |
| `UnexpectedElementException` | 100% | 0 | 9 |
| `Stream` | 100% | 0 | 30 |
| `UnexpectedCharacterException` | 100% | 0 | 12 |
| `Parser` | 100% | 0 | 0 |
| `VersionParser` | 100% | 0 | 55 |
| `Version` | 100% | 0 | 204 |

**Result: 5 / 5 ported Version-core oracle cases pass** against the rule-layer
translation:

- `Version.of(1, 2, 3)` accessors and `str(version)` -> `1.2.3`
- `Version.parse("1.2.3")`
- `Version.parse("1.2.3-alpha.1+build.5")`
- numeric `compareTo` ordering
- `nextPatchVersion()` -> `1.2.4`

## Honest scope and conclusion

- **Demonstrated, not asserted:** external OSS library tests now run against j2py output
  in-repo, hermetically, in `make check`: 14 util tests plus 5 Version-core tests.
- **Mechanical coverage is genuinely high:** 26/26 files parse, zero TODO markers — the
  rule layer is not bluffing about reach.
- **Correctness has a measured, enumerated boundary:** 0 residual translator-defect
  patches are now needed for the util package or the exercised Version-core slice, and
  the generated seven-file Version-core output has 0 `F821` undefined-name findings.

### Remaining full-tree follow-up

1. Add a `jsemver-baseline.json` corpus baseline once the tree is run through
   `translate_corpus.py` so the full-tree node-coverage number is regression-gated.
