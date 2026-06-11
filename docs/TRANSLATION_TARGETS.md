# Translation Target Tests

The normal fixture suite records behavior that j2py already supports as exact Java to
Python fixture pairs. The target suite records roadmap examples and graduated roadmap
fixtures that should keep translating cleanly.

Graduated target fixtures run in `make check`. Only future `xfail` contracts use the
`target_translation` marker and run via `make test-targets`.

Run the normal gate:

```bash
make check
```

Run future roadmap xfail targets:

```bash
make test-targets
```

The suite has three lanes:

- **Graduated targets**: Java fixtures under `tests/fixtures/java/targets/` that now
  translate deterministically. These run in `make check`, must parse, produce valid
  Python, reach `coverage == 1.0`, and report no unhandled diagnostics.
- **Graduated corpus constructs**: Java fixtures under
  `tests/fixtures/corpus/constructs/` that reach the same bar as graduated targets
  (`AdvancedEnum`, `ComplexRecords`, `InterfaceDefaults`, `SealedClasses`,
  `TextBlocks`, `VarKeyword`, `SwitchFallthrough`, `AnonymousAndInner`, `SuperMethodCalls`).
  These also run in
  `make check`.
- **Future targets**: strict `xfail` contracts in `FUTURE_TARGETS` for unsupported
  behavior that should become supported next. Corpus constructs still below full rule
  coverage (`AdvancedStreams`) are included here. These are marked
  `target_translation` and run via `make test-targets`.

Current future corpus-construct backlog:

- Advanced stream collectors and long chains
- Anonymous classes with non-method members and richer inner-class capture
- Switch fall-through and complex switch rule blocks
- Local `var` inference

Each future target case has:

- a Java fixture under `tests/fixtures/java/targets/` or
  `tests/fixtures/corpus/constructs/`
- expected Python fragments that describe the future translation contract
- forbidden fragments such as unsupported TODOs
- a strict `xfail` marker explaining the missing translator capability

When implementing a translation rule:

1. Run `make test-targets` and identify the future or graduated target affected by the
   change.
2. Implement the smallest deterministic rule that makes that target pass.
3. Move or copy the now-supported behavior into the normal fixture suite under
   `tests/fixtures/java/` and `tests/fixtures/python/`.
4. Move the target from `FUTURE_TARGETS` into the graduated fixture check, or delete it
   if the normal fixture fully covers it.
5. Run `make check` and `make test-targets`.

This gives us two signals:

- `make check`: supported behavior and graduated roadmap fixtures must stay green.
- `make test-targets`: future xfail targets alert us when missing behavior unexpectedly
  starts passing.
