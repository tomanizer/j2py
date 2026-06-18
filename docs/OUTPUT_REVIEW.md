# Output Review Guide

j2py output is designed for side-by-side review against the original Java. The goal is
reviewable structural correspondence, not an automatic claim that the Python is production
ready.

## Review Order

1. Check parse and validation status.
2. Review confidence and rule-layer diagnostics.
3. Inspect `TODO(j2py)` and `__j2py_todo__` markers.
4. Read semantic warnings.
5. Compare method order and control flow against Java.
6. Review framework/runtime boundaries manually.
7. Run project-specific tests or equivalence checks.

## Confidence

`confidence` is a user-facing review score surfaced by CLI summaries, JSON output,
reports, dashboards, and the Python API.

It starts from rule-layer node coverage and is capped or dropped when:

- Java parse errors are present;
- semantic warnings exist;
- generated Python syntax is invalid;
- ruff or mypy validation fails;
- post-LLM structural verification fails.

Confidence is not semantic equivalence. A high-confidence file can still require manual
review for business logic, framework behavior, data-access behavior, concurrency, or
reflection.

## Rule Coverage

Raw rule-layer coverage lives on `result.diagnostics.coverage`. It measures handled Java
nodes divided by handled plus unhandled nodes. Semantic warnings do not reduce this raw
coverage; they are reported separately so scoreboards can measure breadth while reviewers
still see risk.

## TODO Markers

j2py emits explicit markers when deterministic translation cannot preserve semantics:

- `# TODO(j2py): ...` comments;
- `__j2py_todo__(...)` sentinel calls;
- `NotImplementedError` stubs for manual-dispatch or unsupported paths.

Treat these as manual review blockers until resolved or intentionally accepted.

## Semantic Warnings

Semantic warnings mark handled constructs that still need attention. Examples include
ambiguous Java behavior, opt-in framework lowering, platform boundaries, and conservative
rewrites where the Python remains syntactically valid but may not preserve runtime
behavior without policy.

Warnings are visible in:

- CLI summaries and JSON output;
- HTML review reports;
- dashboards;
- `j2py doctor` assessments.

## Validation

Validation has three parts:

- Python syntax parsing;
- ruff checks;
- mypy checks.

Install validation tools with:

```bash
pip install --pre "j2py-converter[validate]"
```

Syntactically invalid Python forces confidence to zero. Ruff and mypy failures cap
confidence because the output needs review before it can be used as Python code.

## Structural Verification

After LLM completion, j2py compares Java symbols with the returned Python AST. It checks
class and method presence plus declaration order. Failures cap confidence and trigger a
bounded LLM repair retry.

Rule-only output does not need post-LLM structural verification because it is emitted by
the deterministic pipeline.

## Reports and Dashboards

For a single file or small set of files:

```bash
j2py translate SomeClass.java --report review.html --no-llm
```

For a directory:

```bash
j2py translate src/main/java --output translated_py --dashboard dashboard.html --no-llm
```

Regenerate a dashboard from existing state:

```bash
j2py dashboard translated_py --output dashboard.html
```

Dashboard colors and confidence scores are triage aids. They do not replace side-by-side
review of low-confidence files, files with TODOs, or files that cross framework/runtime
boundaries.

## Framework and Platform Boundaries

j2py lowers common Java/JDK constructs, but it does not emulate application frameworks.
Spring, JPA, servlets, JDBC, reflection, container lifecycle, transaction behavior, and
dependency injection require project policy, config, plugins, or manual porting.

Use:

- [Positioning](POSITIONING.md) for scope boundaries;
- [Framework plugins](FRAMEWORK_PLUGINS.md) for opt-in lowering;
- [Configuration](configuration.md) for `annotation_map`, `import_map`, and related
  project policy.

## Manual Review Checklist

For each translated file, verify:

- class, method, and field order still matches the Java source closely enough for audit;
- overload groups either dispatch deterministically or have explicit manual TODOs;
- integer division, shifts, casts, `get(...)`, and stream operations preserve intended
  semantics;
- exceptions and control flow match the Java structure;
- generated imports refer to real Python modules or intentional project stubs;
- annotation and framework behavior is not silently assumed;
- tests or equivalence checks cover the code path before production use.

## Benchmark Deltas

Corpus benchmarks compare live output against committed baselines. Report both the target
and the direction of change, for example:

```text
make corpus-guava-dense-check
average_coverage: 98.24% -> 99.92% (+1.68%)
full_coverage_files: 145 -> 192 (+47)
Regressions: none
```

`make corpus-hotspots` reads committed baseline JSON only. It is useful for backlog
ranking, but it does not include uncommitted live benchmark improvements until baselines
are intentionally refreshed.
