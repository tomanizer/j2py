# Contributing to j2py

j2py is a general Java-to-Python source translator. Pinned checkouts of popular Java
libraries (Spring Framework, Guava, Apache Commons Lang, Jackson, Caffeine, and others)
appear in this repo only as an external measurement corpus for rule-layer progress — not
as product scope or target runtime.

## Setup

```bash
git clone git@github.com:tomanizer/j2py.git
cd j2py
uv sync --locked
```

Python 3.11 required. `uv` manages the virtualenv automatically.

### Benchmark corpus checkouts (optional, not required for `make check`)

External Java samples (Spring, Guava, Jackson, etc.) live in gitignored checkouts under
`.corpus/`. Clone them once on your main checkout:

```bash
make corpus-clone-all
```

When using a **git worktree**, point at the main checkout's clones instead of
re-downloading:

```bash
export J2PY_CORPUS_ROOT=/path/to/j2py   # directory that contains .corpus/
make corpus-guava-dense-check
```

See [Corpus scoreboard](docs/CORPUS_SCOREBOARD.md) for presets, baselines, and scoreboard
commands.

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

The fixture pair is the contract. CI runs exact fixture equality tests in `make check`.

For unsupported but planned Java constructs, add or update a roadmap target test first.
Graduated target tests live under `tests/targets/` and run in `make check`. Future
`xfail` roadmap contracts use the `target_translation` marker and run with:

```bash
make test-targets
```

Once a target is supported, remove it from `FUTURE_TARGETS` so it runs in the graduated
target check, or move the behavior into the normal fixture suite. See
[Translation Target Tests](docs/TRANSLATION_TARGETS.md) for the target-test workflow and
graduation rules.

For real-corpus progress checks on translation-rule PRs, run `make corpus-clone-all` once,
then compare against committed baselines. At minimum:

```bash
make corpus-spring-dense-check        # Spring dense + construct fixtures
make corpus-guava-dense-check         # or another library preset relevant to the change
make corpus-hotspots                  # optional: cross-library gap triage
```

See [Corpus scoreboard](docs/CORPUS_SCOREBOARD.md) for the full preset table, per-library
baselines, comparison mode, and intentional baseline refresh workflow.

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
4. A `CHANGELOG.md` entry when the change affects user-visible behavior or project
   workflow

## PR rules

- One concern per PR — translation rules, refactor, or docs; not all three
- `Closes #N` in the PR body to auto-close issues (checkboxes in the issue do **not** close it)
- `make ci-local-pr` must pass before requesting review
- No version bumps on feature PRs — version is bumped in a dedicated release PR

## Release

Alpha releases are published to PyPI as the `j2py-converter` distribution. The import
package and console script remain `j2py`; the `j2py` PyPI project name is already owned
by an unrelated project.

Releases are tagged `vX.Y.Z` on `main`; pre-releases use PEP 440 suffixes such as
`v0.1.0a1`. Versioning follows [SemVer](https://semver.org/) for stable releases:

- `MAJOR` — breaking change to `translate_file()` API or output format
- `MINOR` — new Java construct support, new CLI flag
- `PATCH` — bug fix, doc fix, test improvement

Update `CHANGELOG.md`, `pyproject.toml`, and `j2py/__init__.py` in the release PR.
Feature and fix PRs should add notes under `## Unreleased`; the release PR moves those
notes under the tagged version.

Before publishing:

```bash
make release-check
```

The release workflow builds the wheel/sdist and publishes through PyPI trusted
publishing when a GitHub release is published. PyPI trusted publishing is configured for
repository `tomanizer/j2py`, workflow `.github/workflows/publish.yml`, environment
`pypi`, and project `j2py-converter`.
