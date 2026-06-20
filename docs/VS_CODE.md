# VS Code Support

j2py has experimental VS Code support. Treat it as a review convenience, not as the
primary migration interface or a proven IDE product.

The stable workflow today is still the CLI:

```bash
j2py translate Foo.java --output Foo.py
j2py compare Foo.java Foo.py
```

`j2py compare` opens a side-by-side Java/Python diff in VS Code when the `code` command
is available. Use `--editor cursor` or `--editor code-insiders` for other compatible
editors:

```bash
j2py compare Foo.java --editor code --no-llm
j2py compare Foo.java --editor cursor --no-llm
j2py compare Foo.java --no-open --no-llm
```

## Experimental Extension

The repository also contains an experimental VS Code extension under
`packages/j2py-vscode`.

It shells out to the installed `j2py` CLI and currently exposes:

- `j2py: Translate Current File`;
- `j2py: Open Side-by-Side`;
- optional translate-on-save for Java files;
- `TODO(j2py)` and `__j2py_todo__` diagnostics in the Problems panel;
- a status-bar summary with confidence and rule-only/LLM status after translation.

Build it locally from the extension package:

```bash
cd packages/j2py-vscode
npm install
npm run compile
npm run package
```

Install the generated VSIX from VS Code with `Extensions: Install from VSIX...`.

## Settings

| Setting | Meaning |
|---------|---------|
| `j2py.executable` | Path to the `j2py` CLI. Defaults to `j2py`. |
| `j2py.outputDirectory` | Directory for generated Python. Defaults to `${workspaceFolder}/j2py-output`. |
| `j2py.translateOnSave` | Translate saved Java files automatically. Defaults to `false`. |
| `j2py.useLlm` | Allow editor-triggered translation to use LLM completion. Defaults to `false`. |

Example workspace settings:

```json
{
  "j2py.executable": "uv run j2py",
  "j2py.outputDirectory": "${workspaceFolder}/translated_py",
  "j2py.translateOnSave": false,
  "j2py.useLlm": false
}
```

If your editor cannot launch `uv run j2py` as a single executable, create a small wrapper
script and point `j2py.executable` at that script.

## What Is Not Proven Yet

The extension is intentionally marked experimental because it does not yet have:

- automated VS Code extension tests;
- CI coverage for `npm ci`, TypeScript compilation, or VSIX packaging;
- documented manual smoke-test evidence across macOS, Linux, and Windows;
- a mature diagnostics model for `j2py doctor` findings;
- direct SARIF import or SonarQube connected-mode integration;
- command coverage for `doctor`, `sarif`, `wire`, dashboards, or config suggestions.

For assessment findings, use the existing CLI/SARIF path:

```bash
j2py doctor src/main/java --json j2py-assessment.json --include-validation
j2py sarif j2py-assessment.json --output j2py.sarif
```

Use that SARIF file with GitHub code scanning, CI artifacts, a SARIF viewer extension, or
SonarQube Server import. SonarQube for VS Code connected mode should be treated as a
separate workflow until we have tested how imported j2py external issues appear in the
IDE.

## Working With GitHub Copilot

j2py and GitHub Copilot should have different jobs.

j2py should provide deterministic translation, assessment, sidecar metadata, review
artifacts, and validation commands. Copilot should help a reviewer understand findings,
write project-specific glue code, draft tests, and resolve manual migration tasks using
the evidence j2py produced.

Useful integration ideas:

- commit `.github/copilot-instructions.md` for repositories using j2py so Copilot knows
  the migration goal: reviewable Java -> Python correspondence, not unconstrained rewrite;
- add path-specific instructions under `.github/instructions/` for generated Python,
  Java fixtures, framework configs, and `packages/j2py-vscode`;
- expose j2py outputs as Copilot-friendly context: `j2py-assessment.json`, review reports,
  SARIF, sidecars, generated TODO markers, and equivalence-test notes;
- add VS Code commands that copy a focused prompt to Copilot Chat, such as "explain this
  TODO against the Java source", "draft a pytest for this translated method", or "suggest a
  config mapping for this unresolved import";
- add a single `@j2py` chat participant only if the extension needs to control the full
  prompt and orchestrate j2py commands itself;
- prefer VS Code language-model tools or an MCP server if the goal is to let Copilot invoke
  j2py capabilities during an agentic session;
- keep generated edits reviewable by routing Copilot suggestions back through
  `j2py compare`, validation, and equivalence tests.

Good first prompts for Copilot Chat:

```text
Using the original Java file, the generated Python file, and j2py TODO markers, explain
which migration tasks remain. Preserve method order and structural correspondence.
```

```text
Draft pytest tests for the translated Python method using behavior visible in the Java
source. Do not rewrite the implementation.
```

```text
Given this j2py doctor finding and this project config, suggest the smallest explicit
type_map, import_map, or annotation_map change. Do not silently invent framework policy.
```

## Validation Checklist

Before calling the extension production-ready, verify:

1. `npm ci` and `npm run compile` pass in `packages/j2py-vscode`.
2. `npm run package` produces a VSIX.
3. The VSIX installs into a clean VS Code profile.
4. `j2py: Translate Current File` translates a Java fixture into the configured output
   directory.
5. `j2py: Open Side-by-Side` opens the original Java and generated Python.
6. TODO markers appear in the Problems panel.
7. The status bar reports confidence and rule-only/LLM status.
8. Failures from a missing `j2py` executable or invalid CLI JSON are shown as actionable
   editor errors, not silent failures.
9. The CLI path remains usable without the extension.

## Related Docs

- [CLI](CLI.md#j2py-compare) covers the stable `j2py compare` workflow.
- [Output review](OUTPUT_REVIEW.md) explains confidence, warnings, validation, and TODOs.
- [Assessment](DOCTOR.md) covers `j2py doctor`.
- [SARIF](SARIF.md) covers code-scanning export.
