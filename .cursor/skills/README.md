# Cursor agent skills (j2py)

Shared [Cursor agent skills](https://cursor.com/docs/agent/skills) for this repository.
Each skill is a directory with a `SKILL.md` file. Cursor loads skills from
`.cursor/skills/` automatically in this checkout.

**Git worktrees:** `export J2PY_CORPUS_ROOT=/path/to/main/j2py` before corpus or harvest
commands so `.corpus/`, `.env`, and `.j2py/harvest/` resolve correctly.

## Which skill?

```text
Need to find gaps?          → corpus-gap-triage
coverage<1 or unhandled?    → add-translation-rule (or defer → graduate § Defer)
syntax fail, coverage==1?   → harvest-promote
xfail passing / graduate?   → graduate-translation-target
```

## Skills

| Skill | Use when |
|-------|----------|
| [corpus-gap-triage](corpus-gap-triage/SKILL.md) | Hotspots, baselines, gap class → next action |
| [add-translation-rule](add-translation-rule/SKILL.md) | Deterministic rule + Java/Python fixtures |
| [graduate-translation-target](graduate-translation-target/SKILL.md) | Defer (`FUTURE_TARGETS`) or graduate xfails |
| [harvest-promote](harvest-promote/SKILL.md) | LLM harvest promotion + pattern-family issues |

## Typical flow

```text
corpus-gap-triage ──► add-translation-rule ──► graduate-translation-target
        │
        └──► harvest-promote (Tier A / mypy-repair) ──► add-translation-rule
```

## Key docs

- [docs/LLM_HARVEST.md](../../docs/LLM_HARVEST.md)
- [docs/CORPUS_SCOREBOARD.md](../../docs/CORPUS_SCOREBOARD.md)
- [docs/TRANSLATION_TARGETS.md](../../docs/TRANSLATION_TARGETS.md)
- [AGENTS.md](../../AGENTS.md)

## Maintenance

Link integrity is tested in CI: `tests/test_skill_docs.py`.

Other `.cursor/` paths (local IDE config) stay gitignored; only `skills/` is tracked.
