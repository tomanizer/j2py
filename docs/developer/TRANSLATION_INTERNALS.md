# Translation Internals

This is the ownership map for deterministic translation code. Use it before adding a
helper or moving logic between modules.

## Pipeline Shape

The translation path is:

```text
parse -> analyze -> rule-layer skeleton -> optional LLM completion -> validation -> output
```

The rule layer lives mostly under `j2py/translate/`. `j2py/translate/skeleton.py` is the
orchestrating entry point for rule-based output, but new construct work should usually go
into the split modules below it.

## Module Ownership

| Module family | Owns |
|---------------|------|
| `classes.py` | Class-level facade and routing. |
| `class_members.py` | Class-body member traversal. |
| `class_methods.py` | Methods, constructors, parameters, and method body assembly. |
| `class_fields.py` | Field declarations, class/static fields, and field annotations. |
| `class_enums.py` | Java enum lowering. |
| `class_interfaces.py` | Interfaces and abstract base behavior. |
| `class_nested.py` | Nested type handling. |
| `statements.py` | Statement facade and block routing. |
| `stmt_control.py` | `if`, loops, labels, break/continue, and related control flow. |
| `stmt_exceptions.py` | `try`, `catch`, `finally`, throws, and exception mapping. |
| `stmt_switch.py` | Statement-form switch handling. |
| `stmt_sync.py` | `synchronized` statement handling. |
| `expressions.py` | Expression facade. |
| `expr_calls.py` | Method-call router. |
| `expr_collection_calls.py` | Collection-like method calls. |
| `expr_jdk_calls.py` | JDK/platform call lowering that belongs in core. |
| `expr_static_calls.py` | Static and static-import calls. |
| `expr_jdbc_calls.py` | Supported JDBC call scaffolds. |
| `expr_ops.py` | Operator and conditional router. |
| `expr_assignments.py` | Assignment expressions. |
| `expr_binary.py` | Binary operators and Java/Python operator differences. |
| `expr_conditionals.py` | Ternary and conditional expressions. |
| `expr_switch.py` | Switch expressions. |
| `expr_unary.py` | Unary and update expressions. |
| `expr_access.py` | Field, array, and member access. |
| `expr_lambdas.py` | Lambda and functional expression shapes. |
| `expr_objects.py` | Object creation and constructor expressions. |
| `expr_types.py` | Casts, `instanceof`, class literals, and type expressions. |
| `expr_streams.py` | Stream pipeline router. |
| `stream_sources.py` | Stream source chains. |
| `stream_ops.py` | Stream intermediate operations. |
| `stream_collectors.py` | Stream terminal collectors. |
| `rules/` | Pure helpers for imports, literals, naming, static imports, and type mapping. |
| `runtime/` | Python runtime helpers required by emitted code. |

## Choosing The Right Layer

Add a rule when the Java construct can be represented directly in reviewable Python.

Add a helper under `translate/rules/` when the logic is pure, reusable, and does not need
translation context. Naming, type mapping, literals, and import normalization belong here.

Add a runtime helper when emitted Python needs shared behavior that is not a simple syntax
translation. Runtime helpers must be small, documented by tests, and imported through
`TranslationDiagnostics.imports`.

Add a diagnostic when j2py can produce reviewable output but cannot prove semantic
equivalence, or when it must leave a manual port point visible.

Do not add framework behavior to core translation unless an ADR says it belongs there.
Framework-specific extraction belongs in plugins; app assembly belongs in `j2py-wire`.

## Runtime Helper Rules

Runtime helpers are part of generated-output behavior. Treat them as compatibility code:

- keep names stable once emitted by fixtures;
- add direct tests for helper behavior;
- add translation fixtures proving imports are emitted;
- run equivalence tests when a helper changes Java-visible semantics.

Relevant files:

- `j2py/translate/runtime/j2py_runtime.py`
- `tests/translate/test_runtime_dispatch.py`
- `tests/equivalence/`

## Validation

For local translation-rule changes:

```bash
pytest tests/translate -q
make check
```

For runtime-helper semantics:

```bash
pytest tests/translate/test_runtime_dispatch.py -q
make test-equivalence
```

For platform/JDK boundary changes:

```bash
pytest tests/translate/test_platform_imports.py tests/translate/test_runtime_dispatch.py -q
```

## Review Checklist

- The module changed is the owning module for that construct family.
- Shared logic is in a helper only when it is reusable and pure.
- Runtime helpers are tested directly and through generated output.
- Framework and application assembly behavior stays out of core translation.
- The generated Python remains line-level reviewable against the Java source.
