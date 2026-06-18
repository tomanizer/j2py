# Installation

j2py is published as the beta Python package `j2py-converter`. The import package and
CLI command are both `j2py`.

## User install

Install the latest beta:

```bash
pip install --pre j2py-converter
j2py --help
```

Use extras only when you need the matching feature:

```bash
pip install --pre "j2py-converter[yaml]"      # YAML config files
pip install --pre "j2py-converter[validate]"  # ruff + mypy validation
pip install --pre "j2py-converter[gemini]"    # Gemini LLM provider
pip install --pre "j2py-converter[watch]"     # file-watch dependencies
```

The base package includes the Anthropic client. LLM translation requires an API key:

```bash
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
```

Rule-only translation, `j2py doctor`, and corpus scoreboards do not call live LLM APIs.

## Local development

From a clone:

```bash
uv sync --locked
make check
```

For the optional Gemini live probe or harvest commands, use the dev environment because
the `dev` extra includes the Gemini SDK:

```bash
uv sync --locked --extra dev
```

## JDK Requirements

The normal rule-layer tests and `j2py doctor` do not need a JDK. A local JDK is required
for behavior-equivalence tests:

```bash
make test-behavior
```

## Corpus Checkouts

Dense corpus checks use external Java repositories under `.corpus/`. Clone them once in
the main checkout:

```bash
make corpus-clone-all
```

In git worktrees, reuse the main checkout's corpus directory:

```bash
export J2PY_CORPUS_ROOT=/path/to/main/j2py
make corpus-guava-dense-check
```

Do not reclone corpora in every worktree unless you intentionally want separate
checkouts.

## Common Problems

`Validation: ruff, mypy not installed`

Install the validation extra or run with `--no-validate`:

```bash
pip install --pre "j2py-converter[validate]"
j2py translate SomeClass.java --no-validate
```

`--llm-provider gemini` fails with an install hint

Install the Gemini extra:

```bash
pip install --pre "j2py-converter[gemini]"
```

YAML config fails to load

Install the YAML extra:

```bash
pip install --pre "j2py-converter[yaml]"
```

No `.java` files found

`j2py translate`, `j2py analyze`, and `j2py doctor` expect either one Java file or a
directory tree containing `.java` files.

Corpus check cannot find external source files

Run `make corpus-clone-all` in the main checkout, then set `J2PY_CORPUS_ROOT` in the
worktree before running dense checks.

## Next Steps

- [Getting started](GETTING_STARTED.md)
- [CLI reference](CLI.md)
- [Configuration](configuration.md)
- [Corpus scoreboard](CORPUS_SCOREBOARD.md)
