# Vendored fixture: Apache Commons Text `CaseUtils`

The `java/` sources are copied verbatim (Apache License 2.0) from Apache Commons Text
(https://github.com/apache/commons-text), commit
`af9cca805c55f3901d3c904fa0e30cc0feda9457` (post-`1.15.0` `master`).

The post-`1.15.0` `master` revision is pinned deliberately rather than the `1.15.0`
release tag: that revision lowercases with `String.toLowerCase(Locale.ROOT)` and adds the
`testToCamelCaseLocaleIndependent` test. Both exercise translator behavior the release tag
does not (locale-qualified JDK call lowering and locale-independent casing), which is the
point of this case study.

Vendored production sources:

- `org.apache.commons.text.CaseUtils`

`CaseUtilsTest.java` is also vendored as the upstream assertion source for the focused
pytest port in `tests/case_study/test_commons_text_caseutils_case_study.py`. Each file
retains its original ASF license header.

They are vendored so the end-to-end case study
(docs/CASE_STUDY_COMMONS_TEXT_CASEUTILS.md, issue #657) runs hermetically in `make check`
without a corpus checkout. They are inputs to the j2py translator, not j2py source code.
