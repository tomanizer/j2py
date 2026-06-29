# Rule Authoring

Use this guide when adding deterministic translation for a Java construct. The rule layer
is the preferred path whenever j2py can preserve reviewable structure without calling an
LLM.

## What A Good Rule Does

A good rule keeps the Java and Python easy to compare:

- preserves class, method, and control-flow structure where Python allows it;
- converts Java names through the existing naming helpers;
- emits imports through `TranslationDiagnostics.imports`;
- records handled and unhandled constructs honestly;
- leaves unsupported semantics visible as diagnostics or `TODO(j2py)` output;
- adds fixture coverage for the exact Java shape being supported.

Do not make a construct "work" by hiding semantic uncertainty. If the Python output needs
manual review, make that review point explicit.

## Where Code Belongs

| Construct family | Start here | Typical deeper module |
|------------------|------------|------------------------|
| Class declarations and class body routing | `j2py/translate/classes.py` | `class_members.py`, `class_methods.py`, `class_fields.py`, `class_enums.py`, `class_interfaces.py`, `class_nested.py` |
| Statements and blocks | `j2py/translate/statements.py` | `stmt_control.py`, `stmt_exceptions.py`, `stmt_switch.py`, `stmt_sync.py` |
| Expressions | `j2py/translate/expressions.py` | `expr_calls.py`, `expr_ops.py`, `expr_access.py`, `expr_lambdas.py`, `expr_objects.py`, `expr_types.py` |
| Method calls | `j2py/translate/expr_calls.py` | `expr_collection_calls.py`, `expr_jdk_calls.py`, `expr_static_calls.py`, `expr_jdbc_calls.py` |
| Operators and conditionals | `j2py/translate/expr_ops.py` | `expr_assignments.py`, `expr_binary.py`, `expr_conditionals.py`, `expr_switch.py`, `expr_unary.py` |
| Streams | `j2py/translate/expr_streams.py` | `stream_sources.py`, `stream_ops.py`, `stream_collectors.py` |
| Names, types, literals, imports | `j2py/translate/rules/` | `naming.py`, `types.py`, `literals.py`, `imports.py`, `static_imports.py` |
| Name and member binding | `j2py/translate/name_resolution.py` | `member_resolution.py` |
| Runtime behavior that Python must share | `j2py/translate/runtime/j2py_runtime.py` | import through diagnostics helpers |

Use the existing router module when a family already has one. Add a new module only when
the current file is already acting as a dispatcher or the new behavior is a distinct
construct family.

## Step-By-Step

1. Add the smallest representative Java fixture under `tests/fixtures/java/`.
2. Add the expected Python fixture under `tests/fixtures/python/`.
3. Run the fixture test first so you see the current failure.
4. Implement the rule in the owning translation module.
5. Use existing helpers for naming, type mapping, imports, and diagnostics.
6. Re-run the focused fixture test.
7. Run the broader gate listed below.

Prefer one fixture per semantic behavior. If a Java syntax feature has several semantic
shapes, add separate fixtures or a parametrized test rather than one huge example.

## Corpus-Motivated Rules

Corpus scoreboards are breadth signals, not product scope. When a corpus run exposes a
gap, reduce the failing source to the smallest construct family before changing the rule
layer.

For corpus-motivated fixes:

- do not branch on fixture filenames, fixture class names, or one upstream library class;
- add at least one small non-corpus variant, or a parametrized test over the same pattern
  family, unless the change is already covered by an equivalence/behavior fixture;
- prefer `tests/fixtures/java/targets/` for reduced corpus probes that should not affect
  committed corpus baselines;
- keep `tests/fixtures/corpus/constructs/` for graduated mini-corpus coverage that should
  participate in baseline scoreboards;
- run the relevant corpus check after the focused fixture gate so the original evidence
  improves without hiding a different failure.

## Diagnostics And Confidence

Rule coverage is tracked by `TranslationDiagnostics` in
`j2py/translate/diagnostics.py`. A rule should call the existing record/warn paths used by
nearby code:

- handled construct: record it as supported;
- unsupported construct: record it as unhandled;
- translated but review-sensitive construct: record it as handled and add a warning.

Warnings do not reduce raw rule coverage, but they cap user-facing confidence in
`j2py/pipeline.py`. Syntax, ruff, mypy, and structural-verification failures can cap or
zero surfaced confidence. See [Diagnostics](DIAGNOSTICS.md) before changing those rules.

## Tests

Use the narrowest useful test while developing:

```bash
pytest tests/translate -q
pytest tests/translate/skeleton -q
pytest tests/translate/skeleton/test_fixtures.py -q
```

Then run the normal gate:

```bash
make check
```

If the rule affects behavior already covered by literal-oracle tests, run:

```bash
make test-equivalence
make equivalence-report
```

If the rule was motivated by a corpus gap, run the relevant dense check, for example:

```bash
make corpus-commons-lang-dense-check
make corpus-guava-dense-check
make corpus-spring-dense-check
```

Update corpus baselines only after confirming the change is an intentional no-regression
change, not just a different failure shape.

## Review Checklist

- The expected Python is reviewable against the Java source.
- Unsupported semantics remain visible.
- New imports are emitted through `ImportSet`, not hand-spliced into output text.
- Name conversion uses `translate_field_name`, `translate_method_name`, or nearby helpers.
- The fixture fails before the implementation and passes after it.
- Corpus-motivated changes prove the pattern with more than the original corpus example.
- The relevant gate from this guide has been run locally.
