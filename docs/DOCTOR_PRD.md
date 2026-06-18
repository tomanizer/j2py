# Product Requirements Document - j2py doctor

## Goal

`j2py doctor` helps a developer assess a Java codebase before and during migration. It
should answer three practical questions:

1. What can j2py understand today?
2. What is risky or likely to need project policy/manual work?
3. What should the developer run or configure next?

The command is an evidence report, not an authoritative migration planner. It should make
the current migration surface visible without requiring live LLM calls, external corpus
checkouts, or a full Java classpath resolver.

## Users

- **Primary:** A migration developer preparing or iterating on a Java-to-Python port.
  They need a quick project assessment before running bulk translation.
- **Secondary:** Reviewers and technical leads who need a stable JSON/HTML report showing
  migration risk, framework boundaries, and configuration gaps.
- **Tertiary:** Tooling/CI authors who want a machine-readable source of j2py diagnostics
  for SARIF, dashboards, pull request comments, or future IDE integration.

## Current status

The first implementation provides:

- `j2py doctor <file|dir>`
- deterministic `schema_version: 1` JSON output
- static HTML report output
- source/class/method/field inventory from the existing parser/analyzer
- Java parse-error reporting
- dependency-graph translation order and graph warnings
- rule-only translation coverage, confidence, semantic warnings, TODOs, and unhandled
  diagnostics
- annotation inventory
- unresolved import candidates
- conservative advisory config suggestions
- advisory config suggestion export via `--config-suggestions`
- hotspot aggregation for common unhandled nodes, warning reasons, import packages, and
  low-coverage files
- assessment diffs via `j2py doctor diff before.json after.json`
- standalone SARIF export via `j2py sarif j2py-assessment.json --output j2py.sarif`
- optional validation via `--include-validation`

## Functional requirements

### D1 - Run without live LLM

`doctor` must never call provider APIs. It must use deterministic parser, analyzer,
rule-layer translation, diagnostics, and optional local validation only.

### D2 - Accept a Java file or source tree

The command must accept either a single `.java` file or a directory tree. Missing source
paths must return a controlled CLI error, not a traceback.

### D3 - Emit a stable assessment schema

JSON output must be deterministic and versioned. The schema should preserve:

- source path
- summary counts
- per-file parse status
- class, field, and method inventory
- imports and annotations
- rule coverage and surfaced confidence
- semantic warnings and unhandled diagnostics with line numbers where available
- TODO/manual-port markers
- optional validation results
- dependency graph warnings and translation order

### D4 - Emit a static HTML report

HTML output must be self-contained and suitable for local sharing. It should summarize
file risk, parse state, coverage, warnings, unresolved imports, annotation inventory, and
recommended next commands.

### D5 - Classify migration boundaries

`doctor` should identify likely boundary work without deciding project policy:

- JDK/platform APIs needing stubs or project mapping
- Spring/Jakarta/JPA/JDBC/Servlet/framework imports
- external third-party imports
- project-internal imports missing from the scanned source root
- annotations that may need `annotation_map` or framework plugins

### D6 - Provide conservative config suggestions

Config suggestions must be advisory and explicitly low-confidence unless the mapping is
known from current j2py defaults. `doctor` must not silently decide dependency injection,
transactions, persistence, servlet lifecycle, JDBC behavior, or other framework semantics.

Implemented command:

```bash
j2py doctor src/main/java --config-suggestions j2py.suggested.yaml
```

### D7 - Support risk scoring and prioritization

The report should rank files and packages by migration risk using observable evidence:

- parse errors
- unhandled rule-layer constructs
- semantic warnings
- TODO/manual-port markers
- unresolved imports
- framework annotations
- validation failures
- inheritance, nesting, overload, and concurrency complexity

### D8 - Aggregate hotspots

The report includes ranked clusters:

- top unhandled node types
- top semantic-warning reasons
- top unresolved import packages
- top annotation families
- files with the most semantic warnings
- lowest-coverage files

### D9 - Detect project layout

`doctor` should detect common Java project structure:

- Maven `pom.xml`
- Gradle `build.gradle`, `build.gradle.kts`, and `settings.gradle`
- `src/main/java` and `src/test/java`
- multi-module layouts
- configured or inferred Java language level when available

### D10 - Integrate with SARIF

The assessment schema feeds the standalone SARIF exporter from issue #449:

```bash
j2py sarif j2py-assessment.json --output j2py.sarif
```

Future integrated command:

```bash
j2py doctor src/main/java --sarif j2py.sarif
```

### D11 - Support assessment diffs

Users should be able to compare two assessment JSON files to see whether a rule/config
change reduced risk.

Implemented command:

```bash
j2py doctor diff before.json after.json
```

### D12 - Identify equivalence-test candidates

`doctor` should surface methods/classes that are good candidates for literal-oracle
equivalence tests:

- pure utility-style methods
- deterministic inputs and outputs
- no framework/runtime boundary dependencies
- simple project-local dependency surface

### D13 - Produce reusable assessment artifacts

The assessment JSON should be stable enough to feed follow-up j2py tooling such as config
suggestion export, SARIF conversion, stub generation, assessment diffs, dashboards, and
review comments. Current `j2py translate` does not consume assessment JSON directly.
Direct translator consumption should only be added for explicit, reviewable behavior such
as selecting a file subset or applying a reviewed generated config.

## Non-goals

- Full Java compiler/classpath resolution.
- Full-library semantic equivalence proof.
- Live LLM repair or prompt execution.
- Automatic framework migration.
- Automatic generation of production-ready stubs for arbitrary third-party APIs.
- Silently changing translation semantics based on raw assessment findings.
- A promise that risk scoring is a complete migration plan.
- Replacing corpus scoreboards, behavior tests, equivalence tests, or `make check`.

## Success criteria

1. `j2py doctor <src>` runs without LLM API keys.
2. Missing source paths fail with a clean CLI error.
3. JSON output is deterministic and schema-versioned.
4. HTML output is self-contained and usable without network access.
5. Reports distinguish raw rule coverage from surfaced confidence and semantic warnings.
6. Boundary/config suggestions are conservative and reviewable.
7. A migration developer can identify the top files, packages, imports, annotations, and
   rule gaps to address next.
8. The same assessment schema can feed future SARIF, dashboard, and review tooling without
   requiring `translate` to consume raw assessment findings.

## Roadmap

### Phase 1 - Baseline assessment

- JSON and HTML output.
- Parser/analyzer inventory.
- Rule-only translation diagnostics.
- Annotation and unresolved import inventories.
- Conservative config suggestions.
- Advisory config suggestion export.
- Baseline hotspot aggregation.
- Assessment diffing.
- Standalone SARIF export from assessment JSON.

### Phase 2 - Better prioritization

- Build/source-root detection.
- Boundary classification improvements.
- Risk scoring.
- Package-level summaries.
- Richer hotspot aggregation.

### Phase 3 - Workflow integration

- Direct `doctor --sarif` integration.
- Translation-result SARIF export.
- Manual-port report.
- Review dashboard alignment.

### Phase 4 - Migration intelligence

- Stubgen handoff.
- Equivalence-test candidate discovery.
- Optional Java semantic adapters such as JDT LS/OpenRewrite, kept off the default path.
- IDE extension support after the JSON/SARIF contracts are stable.

## References

- [j2py doctor command reference](DOCTOR.md)
- [j2py PRD](PRD.md)
- [Architecture](ARCHITECTURE.md)
- [Framework plugin architecture](FRAMEWORK_PLUGINS.md)
- [JDK lowering vs platform boundaries](decisions/0020-jdk-lowering-vs-platform-boundary-stubs.md)
- [SARIF export](SARIF.md)
