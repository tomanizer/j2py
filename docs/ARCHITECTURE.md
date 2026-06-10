# Architecture — j2py

## Pipeline overview

```
Java source file(s)
        │
        ▼
┌───────────────┐
│   parse/      │  tree-sitter-java → ParsedFile (JavaNode AST + error list)
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   analyze/    │  symbols.py  → FileSymbols (ClassSymbol, MethodSymbol, FieldSymbol)
│               │  graph.py    → DiGraph (dependency edges) → topological order
└───────┬───────┘
        │
        ▼
┌───────────────────────────────────────────────────────┐
│   translate/                                          │
│                                                       │
│   skeleton.py          Rule-based layer               │
│   ├── rules/types.py   Java type → Python type hint   │
│   ├── rules/naming.py  camelCase → snake_case          │
│   ├── rules/literals.py null/true/false/chars         │
│   ├── selectors.py     Declarative AST selectors      │
│   └── transforms.py    Pure transform functions       │
│                                                       │
│   Returns (skeleton_source: str, coverage: float)     │
└───────┬───────────────────────────────────────────────┘
        │  coverage < 1.0
        ▼
┌───────────────┐
│   llm/        │  Claude API (Anthropic SDK)
│               │  prompts.py  → structured system + user messages
│               │  client.py   → disk-cached, tenacity retry
└───────┬───────┘
        │
        ▼
┌───────────────┐
│   validate/   │  ast.parse → ruff check → mypy
│               │  Returns ValidationResult (ok, errors by category)
└───────┬───────┘
        │
        ▼
  Python source file
```

## Component responsibilities

### `parse/` — Java AST extraction
- Wraps `tree-sitter` + `tree-sitter-java` via `JavaNode` and `ParsedFile`
- `JavaNode` provides: `.type`, `.text`, `.location`, `.children`, `.walk()`, `.find_all()`
- Single entry point: `parse_file(path)` or `parse_source(bytes)`
- Surfaces parse errors as `ParsedFile.errors` — does not raise

### `analyze/` — Symbol table and dependency graph
- `symbols.py`: walks the AST to extract `FileSymbols` (package, imports, class list)
- Each `ClassSymbol` holds its fields, methods, superclass, and interface list
- `graph.py`: builds a `networkx.DiGraph` from class-level dependencies and produces
  a topological sort for translation order
- Does not modify the AST or produce any Python output

### `translate/` — Rule-based translation
- `skeleton.py`: orchestrates the rule layer; returns `(python_str, coverage_float)`
  - `coverage = 1.0` means the rule layer handled everything; LLM is skipped
  - Currently a stub (coverage = 0.0) — **primary build target**
- `selectors.py`: CSS-like declarative selectors (`NodeType`, `Text`, `And`, `Or`, `Not`)
  for targeting AST nodes; wire to transform functions as `(Selector, TransformFn)` rules
- `transforms.py`: pure functions `JavaNode → str | None`
- `rules/`: mapping tables and stateless translation functions
  - `types.py`: recursive generic type translation (`List<Map<K,V>>` → `dict[K, V]`)
  - `naming.py`: `camel_to_snake`, `safe_identifier`, reserved-word collision handling
  - `literals.py`: literal token normalisation

### `llm/` — LLM completion
- Called only when `skeleton.py` coverage < 1.0
- `prompts.py`: builds a structured prompt with the Java source, partial skeleton, and
  optional project context; output is plain Python source (no markdown fences)
- `client.py`: Anthropic SDK wrapper; disk-cached at `~/.cache/j2py/llm/`; 3 retries
  with exponential back-off via `tenacity`

### `validate/` — Output validation
- `checks.py`: three-stage check: syntax → ruff → mypy
- Returns `ValidationResult`; never raises; errors are collected, not thrown
- Used by the CLI after writing output; can be run standalone

### `config/` — Layered configuration
- `default.py`: canonical type, collection, exception, import, and literal maps
- `loader.py`: `ConfigLoader` stacks multiple config files (later layers override earlier
  ones for scalars; dicts and sets are merged)
- `TranslationConfig`: Pydantic model; all translation stages accept this as `cfg`

### `pipeline.py` — Orchestrator
- `translate_file(path, cfg, use_llm, model) → TranslationResult`
- Calls parse → analyze → skeleton → (optionally) LLM in sequence
- Single public entry point; CLI and future batch runner both call this

### `cli/` — User interface
- `typer`-based CLI; `j2py translate` and `j2py analyze`
- All output via `rich`; progress bar for directory translation

## Key design decisions

See [docs/decisions/](decisions/) for full ADR context.

| Decision | ADR |
|---|---|
| tree-sitter for parsing | [ADR 0002](decisions/0002-tree-sitter-for-java-parsing.md) |
| Layered rule → LLM pipeline | [ADR 0003](decisions/0003-layered-translation-pipeline.md) |
| Claude (Anthropic) as LLM backend | [ADR 0004](decisions/0004-claude-as-llm-backend.md) |
| Python 3.11+ output with type hints | [ADR 0005](decisions/0005-python-311-target-with-type-hints.md) |

## Dependency rules

- `parse/` has no imports from other j2py packages
- `analyze/` imports `parse/` only
- `translate/` imports `parse/`, `analyze/`, `config/`
- `llm/` imports `config/` only (no parse/translate imports)
- `validate/` imports nothing from j2py
- `pipeline.py` is the single place that imports across all stages
- `cli/` imports `pipeline.py` and `config/` only

These rules keep each stage independently testable.
