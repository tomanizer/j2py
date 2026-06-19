# API Stability

Use this guide when changing public imports, result models, CLI contracts, or experimental
surfaces.

j2py is still beta, but documented surfaces should change deliberately. Users embed j2py
through the CLI, `j2py.pipeline`, config models, doctor facades, and wiring sidecar tools.

## Stability Levels

| Level | Meaning | Examples |
|-------|---------|----------|
| Public | Intended for normal user imports or commands. Changes need docs and compatibility review. | `j2py.pipeline.translate_file`, `TranslationConfig`, `validate_source` |
| Public facade | Supported entry point that wraps internal modules. Keep imports stable even if implementation moves. | `j2py.doctor` facade exports |
| Experimental | Documented but still expected to change. Changes need clear notes and tests, but may be less compatible. | `j2py.wire` Python helpers, VS Code extension |
| Internal | No compatibility promise. Prefer not to document as user API. | Most `j2py.translate.*`, `j2py.parse.*`, `j2py.analyze.*`, `j2py.cli.*` internals |

The [API reference](../API_REFERENCE.md) is the source of truth for supported Python
imports.

## Public Surfaces To Check

When changing API behavior, check:

- [CLI](../CLI.md);
- [API guide](../API.md);
- [API reference](../API_REFERENCE.md);
- [Configuration](../CONFIGURATION.md);
- [Assessment](../ASSESSMENT.md), [Doctor](../DOCTOR.md), and [SARIF](../SARIF.md);
- [Wiring](../WIRING.md) for `j2py-wire`;
- top-level [README](../../README.md) when the behavior is headline-visible.

## Changing Dataclasses Or Result Models

For public dataclasses and result models:

- prefer additive fields with defaults;
- keep existing field names stable;
- avoid changing field meaning without a migration note;
- update JSON output docs and tests when CLI JSON changes;
- update API reference signatures.

Relevant models include:

- `TranslationResult` and `DirectoryTranslationResult` in `j2py/pipeline.py`;
- `ValidationResult` in `j2py/validate/checks.py`;
- doctor facade models exposed through `j2py.doctor`;
- `WiringSidecar` and `WiringElement` in `j2py/wire/schema.py`.

## Deprecation Expectations

When removing or renaming a public surface:

1. Prefer keeping a compatibility wrapper for at least one release cycle.
2. Add a warning or clear docs note when practical.
3. Update changelog or release notes.
4. Update the API reference.
5. Add or update tests proving old and new behavior where compatibility is promised.

For experimental surfaces, a shorter migration note may be enough, but the docs must still
tell users what changed.

## Tests

Run API and CLI tests:

```bash
pytest tests/cli/test_main.py tests/test_pipeline.py -q
```

For config-facing changes:

```bash
pytest tests/config tests/translate/skeleton/test_config.py -q
```

For doctor/SARIF facades:

```bash
pytest tests/test_doctor.py tests/test_sarif.py -q
```

For wiring Python helpers or CLI:

```bash
pytest tests/wire -q
```

## Review Checklist

- The changed surface is classified as public, public facade, experimental, or internal.
- Public changes update the API reference.
- CLI JSON shape changes have tests and docs.
- Compatibility wrappers are kept where users may reasonably rely on them.
- Changelog or release notes are updated when release-facing behavior changes.
