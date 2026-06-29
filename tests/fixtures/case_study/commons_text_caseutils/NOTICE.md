# Vendored fixture: Apache Commons Text `CaseUtils` and `WordUtils`

The `java/` sources are copied verbatim (Apache License 2.0) from Apache Commons Text
(https://github.com/apache/commons-text), commit
`af9cca805c55f3901d3c904fa0e30cc0feda9457` (post-`1.15.0` `master`).

The post-`1.15.0` `master` revision is pinned deliberately rather than the `1.15.0`
release tag: that revision lowercases with `String.toLowerCase(Locale.ROOT)` and adds
locale-independent casing tests for the selected utility classes. Those tests exercise
translator behavior the release tag does not.

Vendored production sources:

- `org.apache.commons.text.CaseUtils`
- `org.apache.commons.text.WordUtils`

`CaseUtilsTest.java` and `WordUtilsTest.java` are also vendored as the upstream assertion
sources for the focused pytest ports in `tests/case_study/`. Each file retains its
original ASF license header.

They are vendored so the end-to-end case study
(docs/CASE_STUDY_COMMONS_TEXT_CASEUTILS.md, issue #657) runs hermetically in `make check`
without a corpus checkout. They are inputs to the j2py translator, not j2py source code.
