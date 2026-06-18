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
pip install --pre "j2py-converter[openai]"    # OpenAI-compatible LLM providers
pip install --pre "j2py-converter[spring]"    # opt-in Spring/FastAPI/SQLAlchemy path
```

The `spring` extra installs FastAPI, HTTPX, SQLAlchemy, and pydantic-settings for
Spring-to-Python migration flows. It does not enable Spring lowering by itself. Spring
marker lowering, framework plugins, wiring metadata, and downstream `j2py-wire` commands
remain explicit runtime choices.

The base package includes the Anthropic client. LLM translation requires an API key:

```bash
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://openai-compatible.example/v1  # optional
```

Rule-only translation, `j2py doctor`, and corpus scoreboards do not call live LLM APIs.

## Local development

From a clone:

```bash
uv sync --locked
make check
```

For optional live provider probes or harvest commands, use the dev environment because the
`dev` extra includes optional provider SDKs:

```bash
uv sync --locked --extra dev
```

For local Spring migration work, include the Spring extra explicitly:

```bash
uv sync --locked --extra spring
uv run --extra spring j2py translate src/main/java --config j2py_config.py --output translated_py
```

The Spring workflow usually also runs `j2py-wire` and the optional smoke test:

```bash
uv run --extra spring j2py-wire --help
uv run --extra spring --extra test pytest tests/integration/test_petclinic_smoke.py -m spring_smoke
```

See [Spring conversion](SPRING_CONVERSION.md) for the full translate -> sidecar ->
`j2py-wire` -> FastAPI smoke path.

Fresh worktrees may need to build the project before the first `uv run`. If the local
`uv` cache is cold, that build resolves backend dependencies such as `hatchling` from
PyPI. In network-restricted environments, pre-warm the cache from the main checkout or
run with an approved temporary cache:

```bash
uv sync --locked --extra dev --extra test --extra validate
UV_CACHE_DIR=/private/tmp/j2py-uv-cache uv run --extra test python -c "import j2py"
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

`--llm-provider openai` fails with an install hint

Install the OpenAI-compatible provider extra:

```bash
pip install --pre "j2py-converter[openai]"
```

`--llm-provider openai` says a model is required

Pass the endpoint's model or deployment ID explicitly:

```bash
j2py translate SomeClass.java --llm-provider openai --model provider-model-id
```

For non-default endpoints, also set `OPENAI_BASE_URL`, `llm_base_url` in config, or
`--llm-base-url` on the command line.

YAML config fails to load

Install the YAML extra:

```bash
pip install --pre "j2py-converter[yaml]"
```

Generated Spring settings or SQLAlchemy modules fail to import

Install the Spring extra in the environment where you import or test generated Spring
outputs:

```bash
pip install --pre "j2py-converter[spring]"
uv sync --locked --extra spring
```

Installing the extra does not change default `j2py translate` behavior. Enable Spring
translation policy explicitly with `annotation_map_preset: spring`, a trusted Python
config that registers framework plugins, and `emit_wiring_metadata = True` when sidecars
are needed.

No `.java` files found

`j2py translate`, `j2py analyze`, and `j2py doctor` expect either one Java file or a
directory tree containing `.java` files.

Corpus check cannot find external source files

Run `make corpus-clone-all` in the main checkout, then set `J2PY_CORPUS_ROOT` in the
worktree before running dense checks.

Fresh worktree benchmark run fails while fetching `hatchling`

This is dependency bootstrap, not a corpus failure. Warm the `uv` cache from the main
checkout with `uv sync --locked --extra dev --extra test --extra validate`, or rerun with
an approved network-capable cache path such as `UV_CACHE_DIR=/private/tmp/j2py-uv-cache`.

`watch` extra seems unused

The current `j2py watch` command polls file hashes and does not require an extra package.
The `watch` optional dependency remains reserved for future watcher implementations.

## Next Steps

- [Getting started](GETTING_STARTED.md)
- [CLI reference](CLI.md)
- [Configuration](configuration.md)
- [Spring conversion](SPRING_CONVERSION.md)
- [Corpus scoreboard](CORPUS_SCOREBOARD.md)
