# Case study - translating Guava Strings end-to-end

Status: **Active** (issue [#658](https://github.com/tomanizer/j2py/issues/658), child
of external-library epic [#655](https://github.com/tomanizer/j2py/issues/655)).

This case study translates a focused Guava `com.google.common.base.Strings` slice with
the deterministic rule layer only, loads the translated class in a small harness, and
runs upstream-derived pytest assertions against the generated Python.

This is the first slice for issue #658, not the whole issue. The tracking issue should
remain open until the remaining candidate slices have been evaluated.

## Why this slice

`Strings` is the smallest high-signal Guava base utility candidate from issue #658. It
exercises null/empty helper delegation, static Guava helper calls, char-array copying,
surrogate-pair checks, `StringBuilder`, varargs, annotation noise, and JDK boundary
imports without pulling in the broader `com.google.common.base` dependency graph.

`Ascii`, `CaseFormat`, and `Optional` remain deferred so this first Guava base PR stays
reviewable and does not close issue #658.

## The subject

[Guava](https://github.com/google/guava), tag `v33.4.8`, commit
`f06690fa3e874f65515e8fd338a74d636e2c792f`, Apache License 2.0.

The hermetic fixture under
[`tests/fixtures/case_study/guava_base_strings/java/`](../tests/fixtures/case_study/guava_base_strings/java)
contains only the scoped production source plus the upstream assertion source:

- `com.google.common.base.Strings`
- `StringsTest.java` for the focused pytest port

## Rule-layer translation metrics

Rule layer only, no LLM (`translate_file(..., use_llm=False, validate=False)`):

| File | Node coverage | `# TODO(j2py)` | Confidence | Semantic warnings |
|---|---:|---:|---:|---:|
| `Strings.java` | 100% | 0 | 0.99 | 32 |

This slice reinforces the case-study theme: 100% node coverage and zero TODOs did not
initially prove executable behavior. The first translated `lenientFormat` body was
structurally complete but still surfaced `GS-1`; that defect is now fixed in the rule
layer and the upstream literal cases run without residual patches.

## Closed loop

The pytest oracle is
[`tests/case_study/test_guava_base_strings_case_study.py`](../tests/case_study/test_guava_base_strings_case_study.py),
backed by
[`tests/case_study/guava_base_strings_harness.py`](../tests/case_study/guava_base_strings_harness.py).

Result: **85 / 85 focused upstream-derived pytest items pass** against the linked
rule-layer translation, plus **4 / 4 harness inventory and exclusion guard tests**.

Covered surface:

- `nullToEmpty`, `emptyToNull`, and `isNullOrEmpty`;
- `padStart` and `padEnd`, including no-padding, some-padding, and negative minimum
  length cases;
- `repeat`, including empty input, the small-count loop, and negative-count failure;
- `commonPrefix`, `commonSuffix`, and `validSurrogatePairAt`, including upstream
  surrogate-pair edge cases encoded as Java-style escape literals;
- executable `lenientFormat` literal cases, including extra arguments, too few
  placeholders, null arguments, and null template handling.

Still deliberately excluded:

- Truth regex matching around `badArgumentToString`, because that path depends on Java
  object/class reflection and exact exception class names;
- the J2KT-specific null `Object[]` varargs case, because Python call syntax cannot
  distinguish one null object from a null varargs array without adding a case-study-only
  sentinel;
- `NullPointerTester`, because it is reflection/testlib infrastructure rather than
  production `Strings` behavior;
- full null-pointer exception-class parity for helper methods; this slice focuses on
  literal return values and the executable negative `repeat` path.

## External-dependency stubs

These are Guava/JDK symbols outside the tested `Strings` logic. They are scaffolding, not
residual translator patches:

- `Platform.nullToEmpty`, `Platform.emptyToNull`, and `Platform.stringIsNullOrEmpty`;
- `Character.isHighSurrogate` and `Character.isLowSurrogate`;
- `Logger.getLogger(...).log(...)` for the excluded bad-argument formatting path.

The harness also reuses the shared test-only `JavaString` and `JavaCharSequence` wrappers
from the equivalence gate so generated calls such as `get_chars(...)` and
`sub_sequence(...)` can execute without pretending Python `str` is a full Java object.

## Residual translator defects

The harness locks active generated-output defects in `_RESIDUAL_GAP_PATCHES`; future
work should keep platform scaffolding separate from this list.

| Gap id | Status | Module | Defect |
|---|---|---|---|
| GS-1 | **Fixed** | `Strings` | `lenientFormat` mutated Python's immutable varargs tuple and lowered `String.valueOf(null)` to `str(None)` instead of Java's `"null"`. Direct varargs parameters now normalize to mutable lists, and `String.valueOf(...)` lowers through a null-safe runtime helper. |

No active residual patches remain for the scoped `Strings` slice.

## Recommended next Guava slice

Continue issue #658 in this order:

1. `Ascii` with `AsciiTest`.
2. `CaseFormat` with `CaseFormatTest`.
3. `Optional` only if the dependency closure stays reviewable.

`Ascii` is the next best Guava base candidate. It keeps the dependency closure smaller
than `CaseFormat` or `Optional`, while exercising ASCII casing, character predicates,
static helpers, and richer primitive/string boundary behavior than `Strings`.
