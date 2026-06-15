# j2py documentation index

## Product and architecture

| Document | Description |
|----------|-------------|
| [PRD.md](PRD.md) | Product goals, functional requirements, non-goals, success criteria |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Pipeline stages, module responsibilities, ADR index |
| [configuration.md](configuration.md) | Config file schema (`j2py.yaml`, TOML, pyproject) |

## Quality, measurement, and roadmap

| Document | Description |
|----------|-------------|
| [TRANSLATION_TARGETS.md](TRANSLATION_TARGETS.md) | Graduated vs future xfail construct workflow |
| [LLM_HARVEST.md](LLM_HARVEST.md) | LLM harvest: batch runs, triage, content cache, promotion pipeline, GitHub issues |
| [CORPUS_SCOREBOARD.md](CORPUS_SCOREBOARD.md) | Multi-library corpus presets, baselines, hotspots |
| [EQUIVALENCE_TESTING.md](EQUIVALENCE_TESTING.md) | Differential testing design (Phase 1 active; CharUtils and NumberUtils literal-oracle gates) |
| [BEHAVIOR_CORPUS.md](BEHAVIOR_CORPUS.md) | JDK-backed stdout/exit-code behavior suite |
| [CASE_STUDY.md](CASE_STUDY.md) | End-to-end multi-file case study (commons-lang `tuple`): what translated, gaps surfaced |

## Process and release

| Document | Description |
|----------|-------------|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Branch workflow, fixtures, material-change rules |
| [../CHANGELOG.md](../CHANGELOG.md) | Version history |
| [RELEASING.md](RELEASING.md) | Alpha release checklist |
| [../SECURITY.md](../SECURITY.md) | Vulnerability reporting |

## Architecture decisions and audits

| Document | Description |
|----------|-------------|
| [decisions/0001-record-architecture-decisions.md](decisions/0001-record-architecture-decisions.md) | ADR process template |
| [ARCHITECTURE.md#key-design-decisions](ARCHITECTURE.md#key-design-decisions) | ADRs 0002–0018 (parser, pipeline, LLM providers, overloads, equivalence, harvest, ...) |
| [decisions/AUDIT-2026-06-15.md](decisions/AUDIT-2026-06-15.md) | Dated maturity and gap audit snapshot |
| [decisions/AUDIT-2026-06-13.md](decisions/AUDIT-2026-06-13.md) | Prior rule-layer breadth snapshot |

## Agent onboarding

| Document | Description |
|----------|-------------|
| [../AGENTS.md](../AGENTS.md) | Agent guidance (mirrored in `CLAUDE.md`) |
| [../.cursor/skills/README.md](../.cursor/skills/README.md) | Cursor agent skills (harvest promotion, etc.) |
