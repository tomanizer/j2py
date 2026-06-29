# Vendored fixture: java-semver (`com.github.zafarkhaja.semver`)

The `java/` sources are copied verbatim (MIT License) from java-semver / jsemver
(https://github.com/zafarkhaja/jsemver), tag `v0.10.2`, commit
`75b5abe97ca55c4569ea84e09330db22a0df2db7`, packages
`com.github.zafarkhaja.semver` and `com.github.zafarkhaja.semver.util`. Each file
retains its original MIT license header.

They are vendored so the end-to-end case study
(docs/CASE_STUDY_JSEMVER.md, issues #613 and #654) runs the `util` and `Version` core
slices hermetically in `make check` without a corpus checkout. They are inputs to the
j2py translator, not j2py source code.

The full library is also pinned as the `jsemver` corpus preset in
`scripts/corpus/corpus_presets.py` for scoreboard / hotspot work over the whole tree.
