# Curated Constructs Mini-Corpus

Small, focused `.java` files that exercise specific Java language constructs for the
j2py rule layer. Density corpus presets mix them in via `--include-constructs` (see
`spring-dense` and `spring-broad` in `scripts/corpus/corpus_presets.py`). External
library checkouts are measurement harnesses only — not product scope.

These files target constructs that are common in large Java codebases but historically
under-covered or challenging for deterministic translation.

## Goals
- **Minimal size**: Each file is intentionally small (typically < 60 LOC) and self-contained.
- **Broad coverage**: Target constructs from the audit gaps and followup roadmap (#47 and children).
- **High signal**: Each file focuses on 1–3 constructs so that `--include-constructs` + density sampling can guarantee progress on them.
- Used by density presets with `--include-constructs` and as regression targets when implementing new rules.

## Current Files (as of latest expansion)

| File                        | Key Constructs Exercised                          | Related Roadmap Item |
|-----------------------------|---------------------------------------------------|----------------------|
| AdvancedEnum.java           | Enum constructors, fields, methods, interface impl, static factories | Enum advanced features (#52) |
| AdvancedStreams.java        | flatMap, reduce, groupingBy+downstream, block lambdas in streams, long chains | Advanced streams |
| AnonymousAndInner.java      | Anonymous classes (expression + stateful), local classes, non-static inner classes with capture | Anonymous + sophisticated inner classes (#50) |
| AmbiguousGetProbe.java      | Calendar API `.get(...)`, list indexing `.get(...)`, map `.get(...)` | Non-collection `.get(...)` disambiguation (#288) |
| ArrayTypeClassLiteral.java  | Array type class literals in runtime class comparisons | Array type class literals (#287) |
| ComplexRecords.java         | Records with compact constructor (validation), custom accessors, static factories, implementing interfaces | Records (modern Java completeness) |
| EnumConstantClassBody.java  | Enum constants with anonymous class bodies overriding abstract methods | Enum constant class bodies (#157) |
| InterfaceDefaults.java      | Interface `default` methods, `static` methods on interfaces | Interface default + static methods (#48) |
| LineCommentInExpression.java | Line comments inside array initializers/expression lists | Line comments in expression contexts (#286) |
| SealedClasses.java          | `sealed` interfaces, `permits`, `non-sealed`, records as permitted types | Sealed classes |
| SuperMethodCalls.java       | `super.method(...)` as statement and return-expression receiver | Super method receiver calls |
| SwitchFallthrough.java      | Intentional fall-through (colon style), complex blocks, switch expressions | Improved switch fall-through + complex rules (#51) |
| TextBlocks.java             | Text blocks with indentation stripping, formatting, `.formatted()`, escapes | Text blocks (#49) |
| VarKeyword.java             | `var` local inference in loops, streams, with generics/casts | Local `var` (modern Java) |

## Usage in Corpus Harness
```bash
# Include these high-signal minimal examples in a density preset run
uv run python scripts/corpus/translate_corpus.py \
  --preset spring-dense --include-constructs --compare-baseline

# Or use convenience targets for presets with committed baselines / exploration
make corpus-spring-dense-check
make corpus-spring-broad            # exploratory; no committed baseline
```

When adding support for a new construct (e.g. one of the remaining gaps), add at least one new minimal file here and ensure it appears in density-based runs.
For corpus-derived fast tests that should not change committed corpus baselines, use
`tests/fixtures/java/targets/` instead.

## Regression tiers

| Tier | Files | How to run |
|------|-------|------------|
| Graduated (`make check`) | `AdvancedEnum`, `AdvancedStreams`, `AnonymousAndInner`, `AmbiguousGetProbe`, `ArrayTypeClassLiteral`, `ComplexRecords`, `EnumConstantClassBody`, `InterfaceDefaults`, `LineCommentInExpression`, `SealedClasses`, `SuperMethodCalls`, `SwitchFallthrough`, `TextBlocks`, `VarKeyword` | `tests/targets/test_translation_targets.py` — `test_graduated_corpus_construct_translates_cleanly` |
| Future xfail (`make test-targets`) | _(none in this directory)_ | `FUTURE_TARGETS` in the same test module |

When a future xfail construct starts passing, move it into the graduated tier (or into
the normal Java/Python fixture pair suite if exact output is stable enough).

## Notes
- Graduated constructs run in `make check`; deferred gaps are tracked outside this
  directory as strict xfails via `make test-targets`.
- Keep each file minimal and parse-clean with tree-sitter-java.
