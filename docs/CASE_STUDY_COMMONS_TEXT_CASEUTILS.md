# Case study - translating Apache Commons Text CaseUtils end-to-end

Status: **Active** (issue [#657](https://github.com/tomanizer/j2py/issues/657), child
of external-library epic [#655](https://github.com/tomanizer/j2py/issues/655)).

This case study is the third external-library closed loop after
[`java-semver`](CASE_STUDY_JSEMVER.md) and
[Apache Commons Codec `Hex`](CASE_STUDY_COMMONS_CODEC_HEX.md). It translates a focused
Apache Commons Text `CaseUtils` slice with the deterministic rule layer only, links the
translated class in a test harness, and runs upstream-derived pytest assertions against
the translated Python.

## Why this slice

The two prior external case studies bias toward byte/array and stream/util constructs.
`CaseUtils.toCamelCase` is the first slice that stresses **string casing, Unicode
code-point iteration, `char...` varargs, and `HashSet<Integer>` membership** end-to-end.
It has a tiny dependency closure (`StringUtils.isEmpty`, `ArrayUtils.isEmpty`, and a few
`java.lang.Character` statics) and a focused upstream test with literal expected values,
which is exactly the profile epic #655 asks for.

It was chosen over the heavier Commons Text surfaces named in #657:

- `WordUtils` (~825 lines, 14 methods) pulls in `Pattern`/`Matcher`, `Validate`, and
  `Strings.CS` — a much wider closure, better as a follow-on.
- `StringEscapeUtils` drags in the translator/lookup machinery and is explicitly
  deferred.

## The subject

[Apache Commons Text](https://github.com/apache/commons-text), commit
`af9cca805c55f3901d3c904fa0e30cc0feda9457` (post-`1.15.0` `master`), Apache License 2.0.
The post-`1.15.0` revision is pinned on purpose: it lowercases via
`String.toLowerCase(Locale.ROOT)` and adds `testToCamelCaseLocaleIndependent`, both of
which exercise translator behavior the `1.15.0` tag does not. See the fixture
[`NOTICE.md`](../tests/fixtures/case_study/commons_text_caseutils/NOTICE.md).

The hermetic fixture under
[`tests/fixtures/case_study/commons_text_caseutils/java/`](../tests/fixtures/case_study/commons_text_caseutils/java)
contains only the scoped production source plus the upstream assertion source:

- `org.apache.commons.text.CaseUtils`
- `CaseUtilsTest.java` for the focused pytest port

## Rule-layer translation metrics

Rule layer only, no LLM (`translate_file(..., use_llm=False, validate=False)`):

| File | Node coverage | `# TODO(j2py)` | Confidence | Semantic warnings |
|---|---:|---:|---:|---:|
| `CaseUtils.java` | 100% | 0 | 0.99 | 6 |

This slice was the sharpest evidence yet that **node coverage and confidence do not prove
executable behavior**: at 100% coverage / 0.99 confidence, the *first* translation of
`toCamelCase` returned the empty string for **every** input (CT-1). None of the 6 semantic
warnings (4 preserved comments, 2 `outOffset++` desugar notes) pointed at any of the
defects below — coverage and confidence were blind to them. The three execution defects
(CT-1, CT-2, CT-3) have since been fixed at the rule layer, so the oracle now runs against
the linked translation with **no residual patches at all**.

## Closed loop

The pytest oracle is
[`tests/case_study/test_commons_text_caseutils_case_study.py`](../tests/case_study/test_commons_text_caseutils_case_study.py),
backed by
[`tests/case_study/commons_text_caseutils_harness.py`](../tests/case_study/commons_text_caseutils_harness.py).

Result: **28 / 28 focused tests pass** against the linked rule-layer translation
(21 parametrized `toCamelCase` assertions ported from upstream, plus supplementary
code-point, locale-independence, constructor, exclusion-guard, and inventory tests).

Covered surface:

- `null` / empty / whitespace-only inputs;
- default-whitespace and explicit `char...` delimiter sets;
- `capitalizeFirstLetter` true/false on the first word;
- multi-delimiter runs and leading-delimiter handling;
- supplementary (astral) code points under the default whitespace delimiter;
- locale-independent casing (`Locale.ROOT` parity via Python `str.lower()`).

## External-dependency stubs

These are JDK / commons-lang3 symbols outside the tested `CaseUtils` logic. They are
scaffolding, not residual translator patches:

- `StringUtils.isEmpty`, `ArrayUtils.isEmpty` (commons-lang3 predicates).
- `java.lang.Character.charCount`, `toTitleCase`, `codePointAt(char[], int)`. Because
  Python `str` is already a sequence of code points (Java models text as UTF-16 code
  units), the stub's `charCount` is always `1`, so the delimiter scan advances in
  code-point space and the algorithm matches.

## Translator defects

The harness locks the **active** generated-output defects in `_RESIDUAL_GAP_PATCHES`,
which is now empty: every execution defect this slice surfaced has been fixed at the rule
layer. Each fix below removed its patch.

| Gap id | Status | Module | Defect and fix |
|---|---|---|---|
| CT-1 | **Fixed** | `CaseUtils` | `new String(int[] codePoints, int offset, int count)` was not lowered — the body fell through to an empty `str()`, so `toCamelCase` always returned `""` with **no diagnostic**. The 3-arg `String(value, offset, count)` constructor now lowers per source-array element type (`int[]` → `chr` per code point, `char[]` → `"".join`, `byte[]` → decode). Fixed in `j2py/translate/expr_objects.py`; covered by `test_new_string_offset_count_constructor_lowers_per_element_kind`. |
| CT-2 | **Fixed** | `CaseUtils` | `String.toLowerCase(Locale.ROOT)` emitted a non-existent `str.to_lower_case(Locale.ROOT)` call and left `Locale` unbound. The single-`Locale` overload of `toLowerCase`/`toUpperCase` now lowers to `str.lower()`/`str.upper()`; ASCII-equivalent locales (`Locale.ROOT`/`ENGLISH`/`US`/…) are exact, others emit a locale-sensitivity warning. Fixed in `j2py/translate/expr_jdk_calls.py`; covered by `test_to_lower_upper_case_locale_overload_lowers_to_python_case` and `test_to_lower_case_locale_sensitive_locale_warns`. |
| CT-3 | **Fixed** | `CaseUtils` | `String.codePointAt(int)` emitted a non-existent `str.code_point_at(index)` call. Now lowers to `ord(str[index])` (mirrors `charAt`'s code-point indexing). Fixed in `j2py/translate/expr_jdk_calls.py`; covered by `test_code_point_at_lowers_to_ord_subscript`. |

A fourth observation is **not** a residual patch but a scoping exclusion:

- **CT-4 (excluded, not patched):** name resolution misroutes `java.lang.Character` into
  the translated package, emitting `from org.apache.commons.text.Character import
  Character`. The harness handles this by import-stripping plus the `Character` stub, so
  no output patch is needed — but the misrouting is a real defect worth a rule-layer fix.
  Separately, the upstream surrogate-pair *delimiter* assertion
  (`toCamelCase(..., '\uD800', '\uDF14')`) is excluded from the oracle: Java combines two
  lone surrogate `char`s in the delimiter array into the supplementary code point
  `U+10314`, which Python's code-point model cannot represent as a delimiter.
  `test_excluded_surrogate_delimiter_case_is_documented` keeps that exclusion explicit.

## Follow-ups

1. ~~CT-1: `String(int[], offset, count)` constructor lowering.~~ **Done.**
2. ~~CT-2 (locale-qualified `toLowerCase`/`toUpperCase`) and CT-3 (`String.codePointAt`).~~
   **Done** — `_RESIDUAL_GAP_PATCHES` is now empty.
3. Fix the `java.lang.Character` name-resolution misrouting (CT-4) so the bogus
   in-package import is not emitted.
4. Expand to `WordUtils` once the string/code-point primitives above are owned by the
   rule layer; defer `StringEscapeUtils` until the lookup machinery has a clear owner.
