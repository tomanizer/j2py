# Parser And Analyzer Internals

Use this guide when changing Java parsing, AST traversal, symbol extraction, or dependency
analysis. Most contributors adding translation coverage do not need this layer; they
should start with [Rule authoring](RULE_AUTHORING.md).

## Ownership

| Area | Modules | Tests |
|------|---------|-------|
| tree-sitter parser setup | `j2py/parse/java_ast.py` | `tests/parse/` |
| Parsed file and AST wrapper | `ParsedFile`, `JavaNode`, `SourceLocation` in `j2py/parse/java_ast.py` | `tests/parse/` and translation fixture tests |
| Symbol extraction | `j2py/analyze/` | `tests/analyze/` |
| Dependency graph behavior | `j2py/analyze/` and architecture docs | `tests/analyze/`; corpus checks when ordering changes |
| Parser design policy | ADR 0002 and ADR 0003 | docs review |

## Parser Contract

`JavaNode` is a thin wrapper around a tree-sitter `Node` plus the original source bytes.
It provides:

- `type` for tree-sitter node type;
- `text` decoded from source byte ranges;
- `location` with 1-based line and 0-based column;
- `children` and `named_children`;
- `child_by_field(...)`, `children_by_type(...)`, `walk()`, and `find_all(...)`.

Keep this wrapper small. Translation modules should not depend on tree-sitter internals
unless `JavaNode` cannot express the required operation.

## Safe Parser Changes

Parser normalization is allowed only when it preserves source locations enough for
reviewable diagnostics. For example, `parse_source` currently normalizes type-use
annotations before varargs ellipses because tree-sitter rejects that shape. The
normalizer replaces removed text with spaces so line and column locations remain useful.

When adding normalization:

- preserve line count;
- preserve byte spans as much as possible;
- document why tree-sitter cannot parse the original shape;
- add a parser test with line and error expectations;
- check that translation diagnostics still point at useful Java lines.

## Analyzer Changes

Analyzer changes are riskier than local translation rules because they can affect
cross-file context, imports, class hierarchy, and LLM context. Keep these changes narrow
and add tests that prove the semantic contract, not just object shape.

Good analyzer tests cover:

- package and class names;
- methods and fields;
- inheritance and implemented interfaces;
- dependency ordering;
- duplicate or nested declarations;
- unresolved symbols that should remain unresolved.

## Validation

Run parser/analyzer tests first:

```bash
pytest tests/parse tests/analyze -q
```

If symbol or dependency ordering can affect generated output, also run:

```bash
make check
```

For cross-file or library-scale effects, add the relevant corpus gate:

```bash
make corpus-hotspots
make corpus-commons-lang-dense-check
make corpus-spring-dense-check
```

## Review Checklist

- `JavaNode` remains a small wrapper, not a translation policy layer.
- Parser normalization preserves diagnostic usefulness.
- Analyzer tests cover the behavior that translation relies on.
- No parser/analyzer change silently changes public output without fixture evidence.
- ADR 0002 or ADR 0003 is still respected, or a new ADR explains the change.
