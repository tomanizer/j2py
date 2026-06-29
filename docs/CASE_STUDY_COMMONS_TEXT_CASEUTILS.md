# Case study - translating Apache Commons Text CaseUtils and WordUtils end-to-end

Status: **Active** (issue [#657](https://github.com/tomanizer/j2py/issues/657), child
of external-library epic [#655](https://github.com/tomanizer/j2py/issues/655)).

This case study is the third external-library closed loop after
[`java-semver`](CASE_STUDY_JSEMVER.md) and
[Apache Commons Codec `Hex`](CASE_STUDY_COMMONS_CODEC_HEX.md). It translates focused
Apache Commons Text `CaseUtils` and `WordUtils` slices with the deterministic rule layer
only, links the translated classes in test harnesses, and runs upstream-derived pytest
assertions against the translated Python.

## Why these slices

The two prior external case studies bias toward byte/array and stream/util constructs.
`CaseUtils.toCamelCase` is the first slice that stresses **string casing, Unicode
code-point iteration, `char...` varargs, and `HashSet<Integer>` membership** end-to-end.
It has a tiny dependency closure (`StringUtils.isEmpty`, `ArrayUtils.isEmpty`, and a few
`java.lang.Character` statics) and a focused upstream test with literal expected values,
which is exactly the profile epic #655 asks for.

`WordUtils` is the next step for #657. Its non-regex word/case/initials surface reuses the
string/code-point primitives from `CaseUtils` but adds Java `Predicate<Integer>` method
references, overload/varargs forwarding, deprecated overload dispatch, `Strings.CS`, and
`Validate`. The first expansion intentionally excludes its regex-heavy `containsAllWords`
and `wrap` methods so the oracle can isolate translator defects before introducing a
`Pattern`/`Matcher` shim.

The remaining heavier Commons Text surface is still deferred:

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
- `org.apache.commons.text.WordUtils`
- `CaseUtilsTest.java` and `WordUtilsTest.java` for the focused pytest ports

## Rule-layer translation metrics

Rule layer only, no LLM (`translate_file(..., use_llm=False, validate=False)`):

| File | Node coverage | `# TODO(j2py)` | Confidence | Semantic warnings |
|---|---:|---:|---:|---:|
| `CaseUtils.java` | 100% | 0 | 0.99 | 6 |
| `WordUtils.java` | 100% | 0 | 0.99 | 42 |

This slice was the sharpest evidence yet that **node coverage and confidence do not prove
executable behavior**: at 100% coverage / 0.99 confidence, the *first* translation of
`toCamelCase` returned the empty string for **every** input (CT-1). None of the 6 semantic
warnings (4 preserved comments, 2 `outOffset++` desugar notes) pointed at any of the
defects below — coverage and confidence were blind to them. The three execution defects
(CT-1, CT-2, CT-3) have since been fixed at the rule layer, so the oracle now runs against
the linked translation with **no residual patches at all**.

`WordUtils` repeats the same lesson: the file translates at 100% node coverage with zero
TODOs, but the first executable expansion needed six residual generated-output patches
before the non-regex oracle could run. WU-1 and WU-5 have since graduated to the rule
layer; the remaining active `WU-*` gaps are locked in the harness until they are fixed
there too.

## Closed loop

The `CaseUtils` pytest oracle is
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

The `WordUtils` expansion is
[`tests/case_study/test_commons_text_wordutils_case_study.py`](../tests/case_study/test_commons_text_wordutils_case_study.py),
using the same harness.

Result: **56 / 56 focused tests pass** against the patched linked rule-layer translation
for the non-regex `WordUtils` surface.

Covered surface:

- `abbreviate` lower/upper bounds and appended suffix behavior;
- `capitalize`, `capitalizeFully`, and `uncapitalize` with default whitespace,
  explicit delimiter lists, and explicit empty `char[]`;
- `initials` with whitespace, custom delimiters, and explicit empty delimiter arrays;
- deprecated `isDelimiter(char, char[])` and `isDelimiter(int, char[])` behavior;
- `swapCase` for upper/lower/title-style word transitions.

Excluded for this phase:

- `containsAllWords`, because it depends on `Pattern.quote`, `Pattern.DOTALL`, matcher
  objects, and Java word-boundary semantics;
- `wrap`, because it depends on iterative regex matching, zero-width matches, system line
  separators, and surrogate-pair hard-wrap behavior.

## External-dependency stubs

These are JDK / commons-lang3 symbols outside the tested `CaseUtils` logic. They are
scaffolding, not residual translator patches:

- `StringUtils.isEmpty`, `ArrayUtils.isEmpty` (commons-lang3 predicates).
- `java.lang.Character.charCount`, `toTitleCase`, `codePointAt(char[], int)`. Because
  Python `str` is already a sequence of code points (Java models text as UTF-16 code
  units), the stub's `charCount` is always `1`, so the delimiter scan advances in
  code-point space and the algorithm matches.
- `WordUtils` additionally stubs scoped `StringUtils.isBlank`, `StringUtils.defaultString`,
  `Strings.CS.indexOf`, and `Validate.isTrue`.

## Translator defects

The harness locks the **active** generated-output defects in `_RESIDUAL_GAP_PATCHES`,
which is now empty: every execution defect this slice surfaced has been fixed at the rule
layer. Each fix below removed its patch.

| Gap id | Status | Module | Defect and fix |
|---|---|---|---|
| CT-1 | **Fixed** | `CaseUtils` | `new String(int[] codePoints, int offset, int count)` was not lowered — the body fell through to an empty `str()`, so `toCamelCase` always returned `""` with **no diagnostic**. The 3-arg `String(value, offset, count)` constructor now lowers per source-array element type (`int[]` → `chr` per code point, `char[]` → `"".join`, `byte[]` → decode). Fixed in `j2py/translate/expr_objects.py`; covered by `test_new_string_offset_count_constructor_lowers_per_element_kind`. |
| CT-2 | **Fixed** | `CaseUtils` | `String.toLowerCase(Locale.ROOT)` emitted a non-existent `str.to_lower_case(Locale.ROOT)` call and left `Locale` unbound. The single-`Locale` overload of `toLowerCase`/`toUpperCase` now lowers to `str.lower()`/`str.upper()`; ASCII-equivalent locales (`Locale.ROOT`/`ENGLISH`/`US`/…) are exact, others emit a locale-sensitivity warning. Fixed in `j2py/translate/expr_jdk_calls.py`; covered by `test_to_lower_upper_case_locale_overload_lowers_to_python_case` and `test_to_lower_case_locale_sensitive_locale_warns`. |
| CT-3 | **Fixed** | `CaseUtils` | `String.codePointAt(int)` emitted a non-existent `str.code_point_at(index)` call. Now lowers to `ord(str[index])` (mirrors `charAt`'s code-point indexing). Fixed in `j2py/translate/expr_jdk_calls.py`; covered by `test_code_point_at_lowers_to_ord_subscript`. |

A fourth observation is **not** a residual patch but a known limitation:

- **CT-4 (known limitation, intentionally not patched):** an unmapped `java.lang.Character`
  reference resolves through the **same-package type fallback**, emitting
  `from org.apache.commons.text.Character import Character`. The case-study harness handles
  it by import-stripping plus the `Character` stub. This initially looked like a simple
  name-resolution bug, but a spike that routed all `JAVA_LANG_BUILTINS` to the implicit
  no-import binding showed it is **load-bearing**: the equivalence gate
  (`BooleanUtils`/`StringUtils`/`NumberUtils` fixtures in `tests/equivalence/`) deliberately
  relies on the same-package fallback to inject stubs at the package path
  (`org.apache.commons.lang3.Character`, `...Boolean`), so removing those imports breaks the
  gate with `NameError`. A real fix would either (a) lower the specific `Character` static
  methods — but `charCount` is entangled with the UTF-16-vs-code-point string model (the
  stub deliberately returns `1` because the rest of the pipeline indexes in code-point
  space), or (b) route `java.lang.Character` to a runtime/platform shim, which is an
  `import_map`/ADR decision rather than a name-resolution change. CT-4 is therefore left as a
  documented convention, not a defect to patch here.
- **Surrogate-pair delimiter (excluded):** the upstream assertion
  `toCamelCase(..., '\uD800', '\uDF14')` is excluded from the oracle: Java combines two
  lone surrogate `char`s in the delimiter array into the supplementary code point
  `U+10314`, which Python's code-point model cannot represent as a delimiter.
  `test_excluded_surrogate_delimiter_case_is_documented` keeps that exclusion explicit.

`WordUtils` active residual patches:

| Gap id | Status | Module | Defect |
|---|---|---|---|
| WU-2 | **Active** | `WordUtils` | Internal forwarding from `capitalizeFully(String, char...)` passes the varargs tuple as one delimiter instead of spreading it. |
| WU-3 | **Active** | `WordUtils` | Merged no-arg/varargs overloads treat omitted delimiters as an explicit empty `char[]`; Java's no-arg overload forwards `null` to mean whitespace. |
| WU-4 | **Active** | `WordUtils` | `Character` case predicates and conversions on int code points lower to Python string APIs on integers, including no-argument `Character.lower()` / `upper()` calls. |
| WU-6 | **Active** | `WordUtils` | The collapsed `isDelimiter` overload dispatcher rejects null delimiter arrays and uses string-only APIs on int code points. |

Graduated `WordUtils` patches:

| Gap id | Status | Module | Defect |
|---|---|---|---|
| WU-1 | **Done** | `WordUtils` | `Predicate<Integer>.test(...)` now lowers to direct callable invocation for typed predicate locals, and collection `::contains` method references lower to Python membership predicates. |
| WU-5 | **Done** | `WordUtils` | `Character.toLowerCase(codePoint)` now preserves the code-point argument and lowers to an int-to-int Python case conversion. |

## Follow-ups

1. ~~CT-1: `String(int[], offset, count)` constructor lowering.~~ **Done.**
2. ~~CT-2 (locale-qualified `toLowerCase`/`toUpperCase`) and CT-3 (`String.codePointAt`).~~
   **Done** — `_RESIDUAL_GAP_PATCHES` is now empty.
3. CT-4 is a documented convention, not a quick fix (see above). If pursued, it needs an
   ADR-level decision: route `java.lang` wrapper types to a runtime shim or `import_map`
   entry, and migrate the equivalence-gate fixtures off the same-package-stub mechanism in
   the same change.
4. Fix WU-2, WU-3, WU-4, and WU-6 in the rule layer, removing each harness patch as it graduates.
5. Add a bounded regex/matcher shim or targeted JDK lowering before expanding to
   `containsAllWords` and `wrap`.
6. Defer `StringEscapeUtils` until the lookup machinery has a clear owner.
