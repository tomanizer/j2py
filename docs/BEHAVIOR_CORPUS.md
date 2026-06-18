# Behavior-equivalence corpus

The behavior corpus is j2py's runtime-correctness gate. Every other check proves the
translated Python is *well-formed* (parses, lints, type-checks, preserves class/method
shape). The behavior corpus proves it is *correct*: each case is compiled and run as
Java, translated **rule-layer-only (no LLM)**, run as Python, and the two are asserted to
produce byte-identical `stdout`, `stderr`, and return code.

## Layout

```
tests/fixtures/behavior/<case_name>/Main.java   # one self-contained program per case
tests/fixtures/behavior/<case_name>/main_class.txt  # optional entry-point override
```

Cases are **auto-discovered** by `tests/behavior/test_equivalence.py`: any directory under
`tests/fixtures/behavior/` containing a `Main.java` becomes a parameterized case. Add a case
by dropping a directory — no test edit required. `scripts/corpus/gen_behavior_corpus.py`
regenerates the curated set and documents the authoring contract.

## Running

```bash
make test-behavior        # requires a local JDK (java + javac)
```

The normal suite (`make check`, no JDK) still runs `test_behavior_corpus_meets_minimum_size`,
which fails if the corpus silently shrinks below its floor.

## Where it runs

| Gate | Trigger | JDK |
|------|---------|-----|
| `.github/workflows/behavior.yml` | PRs/pushes touching `j2py/**` or the corpus | Temurin 17 |
| `make release-check` (`publish.yml`) | release / manual dispatch | Temurin 17 |
| `test_behavior_corpus_meets_minimum_size` | every `pytest` run | none |

Each spawned process is capped (`PROCESS_TIMEOUT_SECONDS`) so a case that loops forever in
Java or in the translated Python fails loudly instead of hanging CI.

## The rule-layer envelope (authoring contract)

The corpus runs **without the LLM**, so every case must stay inside the constructs the
deterministic rule layer translates to *runtime-correct* Python today. This is deliberately
narrow — it is exactly the set j2py can guarantee with zero model involvement. As the rule
layer improves, widen this list and add cases.

## JDK surface demo fixtures

The `jdk_*_surface` cases are original, minimal programs that demonstrate ADR 0020's
JDK policy in executable form: j2py lowers common standard-library usage patterns to
Python expressions and collections, but does not vendor OpenJDK code or ship a Python JDK
compatibility runtime.

These fixtures are suitable for local demos, release notes, and documentation because
they are ordinary behavior-corpus cases:

- `jdk_string_surface`: common `String` instance calls such as `trim`, case conversion,
  `replace`, `contains`, `startsWith`, `split`, `isEmpty`, and `length`.
- `jdk_math_integer_surface`: `Math.abs/max/min` and `Integer.parseInt`.
- `jdk_list_collections_surface`: `List`/`ArrayList` mutation, indexed access, `size`,
  `contains`, enhanced-for iteration, and `Collections.sort`.

Keep future demo fixtures hand-written for j2py. Do not copy, translate, adapt, or vendor
JDK implementation source or Oracle/OpenJDK documentation examples.

**Safe to use**

- Top-level classes only; `main` instantiates (`new Main()`, `new Helper()`) and calls
  **instance** methods. Instance fields, constructors, `this.`/unqualified sibling calls.
- Inheritance via top-level `extends`/`implements`, `super.method()`, abstract classes,
  interfaces, polymorphism through `List<Iface>`.
- Output of **ints and Strings only**.
- Arithmetic with `+ - * %`, Java-style integer `/` and `/=`, parenthesized grouping, and
  bitwise `& | ^`. Comparisons, `&&`/`||`/`!`, ternaries.
- `if`/`else if`/`else`, `while`, `do/while`, counted `for (int i = 0; i < N; i++)`,
  ascending/descending, nested loops, `break`, `continue`, `switch` (in a method).
- Strings: `length`, `charAt`, `substring`, `toUpperCase`, `toLowerCase`, `replace`,
  `trim`, `isEmpty`, `contains`, `startsWith`, `equals`, `split`; `+` concatenation
  **inside `println`**.
- Arrays (`int[]`, `String[]`, `int[][]`): literals, indexing, `.length`, enhanced-for.
- `List<T>` via simple import: `add`, `get`, `size`, `contains`, enhanced-for,
  `Collections.sort`. `Math.max/min/abs`, `Integer.parseInt`.
- Static helper methods calling sibling static methods; methods whose names collide with
  Python builtins, as long as calls stay within the translated class/module.
- `throw new …Exception("msg")`, `try/catch/finally` printing a literal.

**Avoid (known rule-layer gaps — these belong to the LLM layer, not this gate)**

- Printing raw `boolean` (`true`≠`True`), `null` (`null`≠`None`), `float`, or a `char`.
- `String.indexOf`; `StringBuilder`; `Map` / `.put`; enums.
- Nested classes referenced from a `static main`, static fields/constants read from code,
  or classpath-dependent static imports.
- A field and a method with the same name (Java namespaces them; Python does not).
- `string = string + int` outside `println`; `++`/`--` used as a sub-expression.

These avoidances are not arbitrary style rules — each one is a construct where rule-layer
output currently diverges from Java at runtime. They are tracked as rule-layer improvement
opportunities; as each is fixed, a corresponding corpus case should be added here to lock
in the fix.
