# Curated Constructs Mini-Corpus

This directory contains small, focused `.java` files designed to exercise specific Java language constructs that are common in Spring codebases but historically under-covered or challenging for the j2py rule layer.

## Goals
- **Minimal size**: Each file is intentionally small (typically < 60 LOC) and self-contained.
- **Broad coverage**: Target constructs from the audit gaps and followup roadmap (#47 and children).
- **High signal**: Each file focuses on 1–3 constructs so that `--include-constructs` + density sampling can guarantee progress on them.
- Used by `make corpus-spring-broad` / `--include-constructs` and as regression targets when implementing new rules.

## Current Files (as of latest expansion)

| File                        | Key Constructs Exercised                          | Related Roadmap Item |
|-----------------------------|---------------------------------------------------|----------------------|
| AdvancedEnum.java           | Enum constructors, fields, methods, interface impl, static factories | Enum advanced features (#52) |
| AdvancedStreams.java        | flatMap, reduce, groupingBy+downstream, block lambdas in streams, long chains | Advanced streams |
| AnonymousAndInner.java      | Anonymous classes (expression + stateful), local classes, non-static inner classes with capture | Anonymous + sophisticated inner classes (#50) |
| ComplexRecords.java         | Records with compact constructor (validation), custom accessors, static factories, implementing interfaces | Records (modern Java completeness) |
| InterfaceDefaults.java      | Interface `default` methods, `static` methods on interfaces | Interface default + static methods (#48) |
| SealedClasses.java          | `sealed` interfaces, `permits`, `non-sealed`, records as permitted types | Sealed classes |
| SwitchFallthrough.java      | Intentional fall-through (colon style), complex blocks, switch expressions | Improved switch fall-through + complex rules (#51) |
| TextBlocks.java             | Text blocks with indentation stripping, formatting, `.formatted()`, escapes | Text blocks (#49) |
| VarKeyword.java             | `var` local inference in loops, streams, with generics/casts | Local `var` (modern Java) |

## Usage in Corpus Harness
```bash
# Include these high-signal minimal examples
uv run python scripts/corpus/translate_spring_sample.py --include-constructs --strategy density ...

# Or use the convenience target
make corpus-spring-broad
```

When adding support for a new construct (e.g. one of the remaining gaps), add at least one new minimal file here and ensure it appears in density-based runs.

## Notes
- These files are **not** part of the normal `make check` snapshot tests (they live under the corpus harness).
- They are intended to be added to `tests/fixtures/corpus/constructs/` and kept minimal.
- Parse cleanly with tree-sitter-java and produce interesting `handled`/`unhandled` diagnostics when run through the skeleton translator.
