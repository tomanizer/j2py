# Common Failures

## Translation

- Editing `j2py/translate/skeleton.py` when a split module owns the construct.
- Bypassing naming/type/import helpers.
- Treating `ast.parse` as semantic proof.
- Emitting plausible Python for unsupported semantics without warning or `TODO(j2py)`.
- Changing confidence behavior without diagnostics docs and tests.

## Framework And Wiring

- Putting Spring/FastAPI/JPA runtime semantics into core translation.
- Auto-discovering framework plugins from classpaths.
- Creating framework-specific sidecar formats.
- Hiding runtime policy in `j2py-wire` output.
- Forgetting this wording when documenting the boundary:
  j2py writes that metadata to sidecars. `j2py-wire` uses sidecars to generate
  target-stack wiring.

## LLM

- Live provider calls in normal tests, `make check`, or CI.
- Caching truncated completions.
- Prompt changes without prompt-version/cache-key review.
- Using prompts to avoid deterministic rule work.
- Leaking keys or secrets into docs, tests, fixtures, prompts, or output.

## Corpus And Evidence

- Updating corpus baselines without reviewed comparison.
- Treating `spring-dense` as Spring Boot support.
- Treating release notes, case studies, or audits as current command references.
- Moving release evidence into the primary developer task table.
- Claiming a gate passed when it was not run.

## Documentation

- New top-level doc not linked from [docs/README.md](../README.md).
- Agent-only process rule added only to `AGENTS.md` instead of `docs/agents/`.
- New process invented without checking existing User, Developer, Agent, or Repo Hygiene
  sections.
- Renamed doc without test/root-entrypoint updates.
- `AGENTS.md` and `CLAUDE.md` out of sync.
- Headings renamed without anchor check.
- Over-linking every doc from every entry point.

## Drift

- New helper duplicates an existing helper.
- New module created when an owner module already exists.
- New command or Make target created when an existing gate already covers the workflow.
- New doc repeats an existing doc instead of linking to it.
- New abstraction added without a repeated pattern or clear owner boundary.

## Git And Workflow

- Reverting unrelated user changes.
- Destructive Git command without explicit request.
- Staging unrelated dirty files.
- Leaving required command sessions running.
- Pushing a branch with no upstream without `git push -u origin <branch>`.
