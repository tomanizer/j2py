# j2py — Claude Code guidance

## Mission

j2py converts Java source code to semantically and functionally equivalent Python, with
line-level structural correspondence so human review is tractable. The goal is never to
produce "running Python" alone — it is to produce Python that a reviewer can audit
against the original Java class-by-class, method-by-method.

## Key documents — read before working

| Document | What it contains |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Product goals, user stories, non-goals, success criteria |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline stages, component responsibilities, data-flow |
| [docs/decisions/](docs/decisions/) | All ADRs — consult before changing a settled design decision |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branch workflow, PR rules, commit style, changelog |

## Architecture at a glance

```
Java source
    │
    ▼
[parse/]      tree-sitter-java → JavaNode AST, ParsedFile
    │
    ▼
[analyze/]    Symbol table (classes/methods/fields) + dependency graph (networkx)
    │
    ▼
[translate/]  ① Rule-based skeleton (translate/skeleton.py) — target ~70% coverage
              ② Direct visitors: classes.py, statements.py, expressions.py
              ③ Rules sub-package: types, naming, literals
    │
    ▼
[llm/]        Claude fills what the rule layer couldn't reach
              Disk-cached responses; tenacity retry
    │
    ▼
[validate/]   ast.parse → ruff → mypy
    │
    ▼
Python output
```

The rule layer (`translate/skeleton.py`) is implemented and handles many common Java
structures, but it remains incomplete. New deterministic translation work belongs in
`classes.py`, `statements.py`, `expressions.py`, or pure helpers under
`translate/rules/`. The earlier selector/transform prototype has been removed. See
[ADR 0003](docs/decisions/0003-layered-translation-pipeline.md).

## Settled design decisions

Consult ADRs for full context. Do not reverse these without a new ADR:

- **tree-sitter** for Java parsing ([ADR 0002](docs/decisions/0002-tree-sitter-for-java-parsing.md))
- **Layered pipeline**: rule → LLM, not LLM-only ([ADR 0003](docs/decisions/0003-layered-translation-pipeline.md))
- **Claude** as LLM backend ([ADR 0004](docs/decisions/0004-claude-as-llm-backend.md))
- **Python 3.11+** with full type annotations as output target ([ADR 0005](docs/decisions/0005-python-311-target-with-type-hints.md))
- **Line-level structural correspondence** as the quality bar — same method order, same
  control-flow structure, camelCase→snake_case names ([ADR 0003](docs/decisions/0003-layered-translation-pipeline.md))

## Development workflow

```bash
uv run pytest               # run tests
uv run mypy j2py/           # type-check
uv run ruff check j2py/     # lint
uv run ruff format j2py/    # format

make check                  # lint + typecheck + test (run before every commit)
make ci-local-pr            # full local PR check — must pass before pushing
```

All `make` targets must pass locally before pushing. CI gates are identical to local
presets; a red CI means `make check` was not run.

## Code review focus areas

Before approving or merging a PR, verify:

1. **mypy passes** — `make typecheck` clean; no `# type: ignore` without a comment explaining why
2. **Tests cover the change** — new translation rules need parametrised fixture tests
3. **ADR for design changes** — any change to parser, pipeline layering, LLM model/prompt, or
   output format needs either an existing ADR reference or a new ADR
4. **No live LLM calls in normal tests** — tests must not call the Anthropic API
   during `make check`, normal `pytest`, or CI. Use fixtures or stubs by default.
   The only exception is `tests/llm/test_e2e_llm.py`, which must be marked
   `live_llm` and is excluded by pytest configuration unless explicitly run with
   `pytest -m live_llm` and `ANTHROPIC_API_KEY`.
5. **Rule-layer changes have Java fixtures** — `tests/fixtures/java/*.java` + expected `tests/fixtures/python/*.py`
6. **Confidence score honest** — `skeleton.py` coverage estimate must reflect real coverage,
   not be inflated to skip the LLM
7. **Rule-layer helpers stay focused** — keep translation functions stateless where
   possible and use diagnostics when a rule cannot preserve Java semantics

## Writing new ADRs

Create `docs/decisions/NNNN-slug.md` using the template in
[ADR 0001](docs/decisions/0001-record-architecture-decisions.md).

Triggers for a new ADR:
- Changing the parser library
- Changing the LLM provider or model selection strategy
- Adding a new pipeline stage
- Changing the Python output target version
- Changing the translation of any Java construct with non-obvious Python equivalents
  (e.g., choosing `@singledispatch` over overload stubs for method overloading)
