# Contributing to j2py

## Setup

```bash
git clone git@github.com:tomanizer/j2py.git
cd j2py
uv sync --locked
```

Python 3.11 required. `uv` manages the virtualenv automatically.

## Workflow

1. **Branch from `main`**: `git checkout -b feat/my-feature`
2. **Run checks before committing**: `make check` (lint + typecheck + test)
3. **Run `make ci-local-pr`** before pushing — this is what CI runs
4. **Open a PR** using the template — fill every section

### Commit style

```
<type>: <short imperative summary>

<optional body — why, not what>
```

Types: `feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `adr`

Examples:
```
feat: translate enhanced for-loops to Python for comprehensions
fix: preserve Optional<T> in nested generic types
adr: document choice of tree-sitter over javalang (ADR 0002)
```

## Adding a translation rule

Every new Java construct translation needs:

1. **Java fixture** — `tests/fixtures/java/<Feature>.java`
2. **Expected Python fixture** — `tests/fixtures/python/<Feature>.py`
3. **Test** — parametrised entry in `tests/translate/` (or a new test file)
4. **Implementation** — rule in `j2py/translate/rules/` or `skeleton.py`

The fixture pair is the contract. CI snapshot-tests it.

For unsupported but planned Java constructs, add or update a roadmap target test first.
Target tests live under `tests/targets/`, use the `target_translation` marker, and run with:

```bash
make test-targets
```

They are excluded from `make check` until the translator supports the construct. See
[Translation Target Tests](docs/TRANSLATION_TARGETS.md) for the target-test workflow and
graduation rules.

## Material changes

A **material change** is any of:
- Changing how a Java construct is translated (different Python idiom)
- Adding a new pipeline stage
- Changing the LLM model or prompt structure
- Changing the Python output version target
- Breaking the `translate_file()` public API

Material changes require:
1. A new ADR in `docs/decisions/` ([template](docs/decisions/0001-record-architecture-decisions.md))
2. Updated `docs/ARCHITECTURE.md` if the pipeline shape changes
3. Explicit note in the PR body linking the ADR

## PR rules

- One concern per PR — translation rules, refactor, or docs; not all three
- `Closes #N` in the PR body to auto-close issues (checkboxes in the issue do **not** close it)
- `make ci-local-pr` must pass before requesting review
- No version bumps on feature PRs — version is bumped in a dedicated release PR

## Release

Releases are tagged `vX.Y.Z` on `main`. Versioning follows [SemVer](https://semver.org/):

- `MAJOR` — breaking change to `translate_file()` API or output format
- `MINOR` — new Java construct support, new CLI flag
- `PATCH` — bug fix, doc fix, test improvement

Update `CHANGELOG.md` and `pyproject.toml` version in the release PR.
