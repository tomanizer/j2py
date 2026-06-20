# Release records

Release evidence is stored under one directory per published version:

```text
docs/releases/<version>/
```

Each release directory uses fixed filenames so tests and docs can resolve the current
release from `pyproject.toml` without adding version-stamped filenames to every release:

| File | Purpose |
|------|---------|
| `RELEASE_NOTES.md` | User-facing release story, scope, quality evidence, and known limits. |
| `TEST_EVIDENCE.md` | Claim-to-evidence inventory for release-facing behavior. |
| `CANDIDATE_EVIDENCE.md` | Package build, clean install smoke, and pre-tag checklist evidence. |
| `DOCUMENTATION_AUDIT.md` | Docs audit against current CLI help, config schema, fixtures, and generated output. |
| `PERFORMANCE_BASELINE.md` | Local translation, framework smoke, and corpus/reporting performance notes. |
| `DIAGNOSTICS_TODO_AUDIT.md` | Diagnostics and TODO wording audit for release boundaries. |

Keep release records as snapshots. Update live command references in the user or
developer docs first, then link from the release notes to the evidence that was actually
run for that version.
