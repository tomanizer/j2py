# Developer Change Guides

These guides are for contributors changing j2py itself. They complement the main
[developer docs index](../README.md#developer-docs): start from that task map, then use
the relevant guide here when you need subsystem-level detail.

Each guide should answer three questions:

1. Which modules own this behavior?
2. What contract must a change preserve?
3. Which tests or local gates prove the change?

## Guides

Core translation:

| Guide | Use it when |
|-------|-------------|
| [Rule authoring](RULE_AUTHORING.md) | Adding or changing deterministic Java-to-Python translation rules. |
| [Parser and analyzer internals](PARSER_ANALYZER.md) | Changing tree-sitter parsing, `JavaNode`, symbol extraction, or dependency graph behavior. |
| [Translation internals](TRANSLATION_INTERNALS.md) | Deciding where translation code belongs across class, statement, expression, helper, and runtime modules. |
| [Diagnostics](DIAGNOSTICS.md) | Adding diagnostics, TODO markers, confidence behavior, validation output, doctor findings, or SARIF mappings. |

Frameworks and app assembly:

| Guide | Use it when |
|-------|-------------|
| [Framework plugin authoring](FRAMEWORK_PLUGIN_AUTHORING.md) | Writing trusted framework plugins and sidecar metadata tests. |
| [Wiring targets](WIRING_TARGETS.md) | Adding or changing a `j2py-wire generate --target ...` backend. |

Tooling and public surfaces:

| Guide | Use it when |
|-------|-------------|
| [LLM providers](LLM_PROVIDERS.md) | Changing LLM provider calls, prompts, caches, retries, or live-test boundaries. |
| [Validation gates](VALIDATION_GATES.md) | Choosing the right local test or Makefile gate for a change. |
| [VS Code extension](VS_CODE_EXTENSION.md) | Working on `packages/j2py-vscode`. |
| [API stability](API_STABILITY.md) | Changing public Python imports, CLI/API contracts, or experimental surfaces. |

For user-facing command behavior, prefer [CLI](../CLI.md), [API guide](../API.md), and
[API reference](../API_REFERENCE.md). For historical evidence, release notes, and audits,
use the repo hygiene section in the main docs index instead of these change guides.

Coding agents should also read [Coding Agent Guides](../agents/README.md). Those guides
compress this developer section into task routing, validation gates, docs-update targets,
and common failure checks for automated repo work.
