# Cursor agent skills (j2py)

Shared [Cursor agent skills](https://cursor.com/docs/agent/skills) for this repository.
Each skill is a directory with a `SKILL.md` file. Cursor loads skills from
`.cursor/skills/` automatically when working in this checkout.

| Skill | Use when |
|-------|----------|
| [harvest-promote](harvest-promote/SKILL.md) | Running the LLM harvest promotion pipeline, refreshing the queue, or filing pattern-family GitHub issues |

Operator guide for harvest: [docs/LLM_HARVEST.md](../../docs/LLM_HARVEST.md).

Other IDE state under `.cursor/` (rules, local config) stays gitignored.
