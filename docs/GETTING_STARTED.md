# Getting Started

This walkthrough uses the CLI path a migration reviewer is most likely to take:
install, assess, configure, translate, and review.

## Choose the right path

### Simple path

For simple Java, start with the core translator and review output:

```bash
j2py translate Foo.java
j2py compare Foo.java Foo.py
```

### Enterprise path

For enterprise or framework-heavy code, use the full pipeline described in
[Positioning and enterprise scope](POSITIONING.md#one-pipeline-five-layers):

```bash
j2py doctor project/
# create and review config
j2py translate project/ --config j2py_config.py --output translated_py
j2py-wire list translated_py
j2py-wire generate translated_py --target fastapi
j2py-wire validate translated_py
```

You do not need framework plugins or `j2py-wire` for framework-light Java.

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

## 2. Smoke-Test One Tiny File

Before pointing j2py at a real project, verify the installed CLI with a small Java file:

```bash
mkdir -p /tmp/j2py-smoke/src/main/java/demo
cat > /tmp/j2py-smoke/src/main/java/demo/HelloWorld.java <<'JAVA'
package demo;

public class HelloWorld {
    private final String name;

    public HelloWorld(String name) {
        this.name = name;
    }

    public String greeting() {
        return "Hello, " + name;
    }
}
JAVA

j2py translate /tmp/j2py-smoke/src/main/java \
  --output /tmp/j2py-smoke/translated_py \
  --no-llm \
  --no-validate

python -m py_compile /tmp/j2py-smoke/translated_py/demo/HelloWorld.py
```

The output path preserves the Java package structure. In this example the generated file
is `/tmp/j2py-smoke/translated_py/demo/HelloWorld.py`.

Use `--no-validate` for the first smoke test unless you installed the `validate` extra.
Use `--no-llm` until the deterministic output and diagnostics are clear.

## 3. Assess the Java Source

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

For details, see [Assessment](DOCTOR.md), [j2py doctor](DOCTOR.md), and
[SARIF export](SARIF.md).

## 4. Add Project Config

j2py auto-discovers the first supported config file under the project root:

- `j2py.yaml`
- `j2py.yml`
- `j2py.toml`
- `[tool.j2py]` in `pyproject.toml`

Use config for project-specific type, import, exception, literal, and annotation mappings:

```yaml
type_map:
  Money: Money
  Logger: logging.Logger

import_map:
  com.acme.money.Money: "from acme.money import Money"
  org.slf4j.Logger: "import logging"

drop_annotations:
  - Override

annotation_map:
  org.springframework.web.bind.annotation.RestController:
    python_decorator: rest_controller
    import: "from acme.web import rest_controller"
```

See [Assessment](DOCTOR.md), [Configuration](CONFIGURATION.md),
[Framework plugins](FRAMEWORK_PLUGINS.md), and [Wiring](WIRING.md).

## 5. Translate Without LLM First

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

## 6. Generate Review Artifacts

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

## 7. Review Side by Side

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

## 8. Add LLM Completion Deliberately

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

## 9. Measure Rule-Layer Breadth

Corpus scoreboards are regression signals over pinned external samples, not proof of
enterprise readiness:

```bash
make corpus-guava-dense-check
make corpus-spring-dense-check
make corpus-hotspots
```

When running from a worktree, set `J2PY_CORPUS_ROOT` to the main checkout. See
[Corpus scoreboard](CORPUS_SCOREBOARD.md).

## 10. Try The Spring Conversion Path

Skip this section unless your source project uses Spring. Spring conversion is opt-in and
split across two tools: `j2py translate` emits translated Python plus framework sidecars,
then `j2py-wire` consumes those sidecars and generates FastAPI wiring.

For an installed environment, verify that the Spring extra is present:

```bash
pip install --pre "j2py-converter[spring]"
j2py-wire --help
python -c "import fastapi, sqlalchemy, httpx, pydantic_settings"
```

For local repository work, start with the executable smoke gate:

```bash
make test-spring-smoke
```

The smoke gate translates a constrained PetClinic owner slice, emits real Spring wiring
sidecars, runs `j2py-wire generate`, runs `j2py-wire validate`, starts a FastAPI
`TestClient`, and checks the owner endpoints. For the full workflow, configuration, and
limits, see [Spring conversion](SPRING_CONVERSION.md).

## Where to Go Next

- [CLI reference](CLI.md)
- [Python API Guide](API.md)
- [Python API Reference](API_REFERENCE.md)
- [Output review](OUTPUT_REVIEW.md)
- [Positioning](POSITIONING.md)
- [Configuration](CONFIGURATION.md)
- [Spring conversion](SPRING_CONVERSION.md), only for Spring source projects
