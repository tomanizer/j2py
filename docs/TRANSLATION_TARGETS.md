# Translation Target Tests

The normal fixture suite records behavior that j2py already supports. The target suite
records behavior j2py needs to support next.

Target tests are allowed to fail today. They are marked with `target_translation` and
excluded from `make check` so roadmap work can add realistic Java examples before the
translator can handle them.

Run the normal gate:

```bash
make check
```

Run the roadmap target scoreboard:

```bash
make test-targets
```

Each target case has:

- a Java fixture under `tests/fixtures/java/targets/`
- expected Python fragments that describe the future translation contract
- forbidden fragments such as unsupported TODOs
- a strict `xfail` marker explaining the missing translator capability

When implementing a translation rule:

1. Run `make test-targets` and identify the xfail target that should become supported.
2. Implement the smallest deterministic rule that makes that target pass.
3. Move or copy the now-supported behavior into the normal fixture suite under
   `tests/fixtures/java/` and `tests/fixtures/python/`.
4. Remove the `xfail` mark for the target, or delete the target if the normal fixture
   fully covers it.
5. Run `make check` and `make test-targets`.

This gives us two signals:

- `make check`: supported behavior must stay green.
- `make test-targets`: roadmap behavior shows what is still missing and alerts us when
  a target unexpectedly starts passing.
