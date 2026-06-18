# Getting Started

This walkthrough uses the CLI path a migration reviewer is most likely to take:
install, assess, configure, translate, and review.

## 1. Install

```bash
pip install --pre j2py-converter
j2py --help
```

For local development in this repository:

```bash
uv sync --locked
uv run j2py --help
```

See [Installation](INSTALL.md) for optional extras, API keys, JDK requirements, and
corpus setup.

## 2. Assess the Java Source

Run `doctor` before translating a project. It is rule-only and does not call an LLM:

```bash
j2py doctor src/main/java \
  --json j2py-assessment.json \
  --html j2py-assessment.html \
  --config-suggestions j2py.suggested.yaml
```

Use the report to identify parse failures, unresolved imports, annotations, TODO
markers, semantic warnings, and low-coverage files. The generated config suggestions are
advisory; review them before using them as real config.

For details, see [j2py doctor](DOCTOR.md) and [SARIF export](SARIF.md).

## 3. Add Project Config

j2py auto-discovers the first supported config file under the project root:

- `j2py.yaml`
- `j2py.yml`
- `j2py.toml`
- `[tool.j2py]` in `pyproject.toml`

Use config for project-specific type, import, exception, literal, and annotation
mappings:

```yaml
import_map:
  com.acme.money.Money: acme.money.Money
  org.slf4j.Logger: logging.Logger

drop_annotations:
  - Override

annotation_map:
  org.springframework.web.bind.annotation.RestController:
    python_decorator: fastapi_router
    import: acme.web.fastapi_router
```

See [Configuration](configuration.md) and [Framework plugins](FRAMEWORK_PLUGINS.md).

## 4. Translate Without LLM First

Start with deterministic translation:

```bash
j2py translate src/main/java --output translated_py --no-llm
```

For a single file:

```bash
j2py translate src/main/java/com/acme/OrderService.java --no-llm --dry-run
```

Directory translation preserves package-relative output paths, translates in dependency
order, writes `.j2py-state.json`, and can skip unchanged files on later runs:

```bash
j2py translate src/main/java --output translated_py --no-llm --incremental
```

## 5. Generate Review Artifacts

For one file, write a side-by-side HTML report:

```bash
j2py translate src/main/java/com/acme/OrderService.java \
  --output translated_py/OrderService.py \
  --report order-review.html \
  --no-llm
```

For a directory, write a dashboard:

```bash
j2py translate src/main/java \
  --output translated_py \
  --dashboard dashboard.html \
  --no-llm
```

Regenerate the dashboard later from the output directory state:

```bash
j2py dashboard translated_py --output dashboard.html
```

For an additional non-mutating review pass, ask the configured LLM provider to audit the
generated output and write machine-readable findings:

```bash
j2py translate src/main/java \
  --output translated_py \
  --no-llm \
  --llm-review \
  --llm-review-scope warnings \
  --review-report j2py-review.json
```

LLM review findings do not repair output or change confidence; treat them as prompts for
human review.

## 6. Review Side by Side

Open a Java/Python diff in VS Code or Cursor:

```bash
j2py compare src/main/java/com/acme/OrderService.java --no-llm
j2py compare src/main/java/com/acme/OrderService.java --editor cursor --no-llm
```

To print the paths and editor command without opening an editor:

```bash
j2py compare src/main/java/com/acme/OrderService.java --no-open --no-llm
```

See [Output review](OUTPUT_REVIEW.md) for how to interpret confidence, warnings,
TODO markers, validation, and structural verification.

## 7. Add LLM Completion Deliberately

LLM completion is optional. Use it after rule-only output has made the deterministic
boundary clear:

```bash
ANTHROPIC_API_KEY=... j2py translate src/main/java/com/acme/OrderService.java
```

Gemini requires the optional extra and API key:

```bash
pip install --pre "j2py-converter[gemini]"
GEMINI_API_KEY=... j2py translate SomeClass.java \
  --llm-provider gemini \
  --model gemini-3.5-flash
```

OpenAI-compatible endpoints require the optional OpenAI extra, an API key, and an
endpoint-specific model ID:

```bash
pip install --pre "j2py-converter[openai]"
OPENAI_API_KEY=... j2py translate SomeClass.java \
  --llm-provider openai \
  --llm-base-url https://openai-compatible.example/v1 \
  --model provider-model-id
```

## 8. Measure Rule-Layer Breadth

Corpus scoreboards are regression signals over pinned external samples, not proof of
enterprise readiness:

```bash
make corpus-guava-dense-check
make corpus-spring-dense-check
make corpus-hotspots
```

When running from a worktree, set `J2PY_CORPUS_ROOT` to the main checkout. See
[Corpus scoreboard](CORPUS_SCOREBOARD.md).

## Where to Go Next

- [CLI reference](CLI.md)
- [Python API](API.md)
- [Output review](OUTPUT_REVIEW.md)
- [Positioning](POSITIONING.md)
