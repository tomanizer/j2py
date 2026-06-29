# Vendored fixture: Guava `Strings`

The `java/` sources are copied verbatim (Apache License 2.0) from Guava
(https://github.com/google/guava), tag `v33.4.8`, commit
`f06690fa3e874f65515e8fd338a74d636e2c792f`.

Vendored production source:

- `com.google.common.base.Strings`

`StringsTest.java` is also vendored as the upstream assertion source for the focused
pytest port in `tests/case_study/test_guava_base_strings_case_study.py`. Each file
retains its original Apache License 2.0 header.

They are vendored so the end-to-end case study
(docs/CASE_STUDY_GUAVA_BASE_STRINGS.md, issue #658) runs hermetically in `make check`
without a corpus checkout. They are inputs to the j2py translator, not j2py source code.
