# Changelog

All notable changes to j2py will be documented in this file.

The format follows the repository commit types: `feat`, `fix`, `refactor`, `test`,
`docs`, `chore`, and `adr`.

## Unreleased

### Added

- Initial deterministic skeleton translator for simple Java classes.
- Structured rule-layer diagnostics and coverage reporting.
- Spring corpus scoreboard with a pinned baseline.
- Roadmap target tests for unsupported Java-to-Python constructs.
- Support for translating if/else, classic for/while/do-while, try/catch/finally, throw, break/continue.
- Expanded expression support (ternaries, class literals, array access, updates, common collection and string idioms).
- Full support for nested type declarations (interfaces as Protocol, enums as Enum, records as frozen dataclass).
- Simple overload handling and improved constructor support.
- Config-driven import emission (respecting import_map, drop_imports, plus auto-adds for dataclass/Enum/Protocol/overload/Any).
- Dependency-ordered directory translation using the symbol graph.
- Clean comment preservation (line and block/Javadoc) without impacting coverage metrics.
- Full exposure of diagnostics and validation results on TranslationResult and in CLI output.
- LLM hardening: API key preflight, richer cache keys (including diagnostics, validation feedback, config fingerprint, prompt version).
- Translation target scoreboard (`make test-targets`) and improved corpus comparison workflow (`make corpus-spring`).
- Expanded test coverage (CLI, config, LLM stubs, validate, graph, etc.) and CHANGELOG.md.

### Changed

- Split skeleton translation into class, statement, expression, diagnostic, and node helper
  modules.
- Removed unused declarative selectors/transforms prototype (now purely imperative visitors in the rule layer, matching actual implementation).
- Updated docs (README, ARCHITECTURE, new TRANSLATION_TARGETS.md / CORPUS_SCOREBOARD.md) to accurately reflect current capabilities vs. roadmap.
- CLI now reports translation order, per-file confidence/handled/unhandled/LLM usage, cycle warnings, and validation status. Directory mode exits non-zero on validation failures when --validate is used.

### Removed

- Unused `libcst` dependency (no longer referenced in source).

## v0.1.0 (previous baseline)
