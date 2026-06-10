# ADR 0002 — Use tree-sitter for Java parsing

**Date:** 2026-06-10
**Status:** Accepted

## Context

j2py needs to parse Java source files into a rich AST for analysis and translation.
Candidate libraries evaluated:

| Library | Grammar currency | Python binding | Notes |
|---|---|---|---|
| `tree-sitter` + `tree-sitter-java` | Java 21 | First-class | Used by GitHub, Neovim, VS Code |
| `javalang` | Java 8 (2015) | Native Python | No lambdas, records, text blocks |
| ANTLR 4 + Java grammar | Java 21 | Via `antlr4-python3-runtime` | JVM toolchain dependency; grammar maintenance burden |
| `srcML` | Java 11 | CLI subprocess | XML output; external binary |

`javalang` is pure Python but frozen at Java 8 — it cannot parse lambdas, streams,
records, sealed classes, or text blocks, all of which appear in modern Java codebases.

ANTLR requires a JVM to generate the parser from grammar; adds installation complexity
and a Java dependency to a Python tool.

`tree-sitter-java` is maintained as part of the tree-sitter ecosystem, tracks the Java
grammar actively, and has a stable `tree-sitter` Python binding (`tree-sitter>=0.23`).

## Decision

Use `tree-sitter` + `tree-sitter-java` as the sole Java parser. Wrap it in
`j2py/parse/java_ast.py` behind the `JavaNode` / `ParsedFile` interface so that the
rest of the codebase has no direct tree-sitter dependency.

## Consequences

+ Handles Java 8–21 including lambdas, records, sealed classes, text blocks
+ Maintained by the tree-sitter community; grammar updates are pip upgrades
+ Consistent with how editors (VS Code, Neovim) parse Java — well-tested on real corpora
+ Pure Python; no JVM required at runtime
− tree-sitter AST is a CST (includes whitespace/comment nodes) — slightly more noise
  to filter than a pure AST; handled by the `named_children` / `find_all` helpers
− Grammar updates (via pip) could change node type names; pin `tree-sitter-java` in
  `pyproject.toml` and review grammar changelog on upgrades

## References

- tree-sitter-java: https://github.com/tree-sitter/tree-sitter-java
- javalang: https://github.com/c2esmoe/javalang (archived)
