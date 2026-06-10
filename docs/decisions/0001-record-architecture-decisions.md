# ADR 0001 — Record architecture decisions

**Date:** 2026-06-10
**Status:** Accepted

## Context

j2py is a non-trivial translation tool with several design dimensions that have
non-obvious trade-offs: parser choice, pipeline layering, LLM provider, output format.
Future contributors (including Claude and other agents) need to understand *why* choices
were made, not just *what* was chosen.

## Decision

We record architecture decisions as ADRs in `docs/decisions/NNNN-slug.md`.

**Template:**

```markdown
# ADR NNNN — Title

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded by NNNN

## Context
The situation and forces that drove this decision.

## Decision
What we decided to do.

## Consequences
Positive and negative outcomes. Mark anything still uncertain.

## References
Links to PRs, issues, or external sources.
```

**When to write an ADR:**
- Changing the Java parser library
- Changing the LLM provider or model selection strategy
- Adding or removing a pipeline stage
- Changing the Python output target version
- Choosing a non-obvious translation for a Java construct
  (e.g., how to handle method overloading)

**Numbering:** sequential integers with four-digit zero-padding. No reuse of numbers,
even for superseded ADRs.

## Consequences

+ Decisions are traceable and reviewable
+ Agents (Claude, Copilot) can consult ADRs before reversing settled choices
− Writing ADRs takes time; we limit them to genuinely settled or consequential decisions

## References

- Inspired by Michael Nygard's original ADR format
- frtb-capital ADR practice
