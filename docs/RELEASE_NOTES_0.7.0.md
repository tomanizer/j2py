# j2py 0.7.0 Release Notes

0.7.0 is the first j2py release aimed at real migration trials outside the project. The
release story is deliberately narrow: j2py translates Java source into reviewable Python,
provides evidence about what was translated deterministically, and offers opt-in
Spring/FastAPI/SQLAlchemy scaffolding for bounded application slices.

It is not a JVM, JDBC bridge, Spring container, Hibernate runtime, or automatic full
application migration tool.

## Headline

j2py 0.7.0 provides a deterministic Java-to-Python translation workflow with review
artifacts, diagnostics, corpus/equivalence quality gates, and an opt-in Spring conversion
path that can emit FastAPI/SQLAlchemy scaffolding from explicit project configuration.

## What Users Get

- **Rule-layer Java translation** for common classes, methods, fields, constructors,
  records, enums, interfaces, anonymous/local helpers, streams, overloads, control flow,
  collection calls, JDK call lowering, and package-ordered directory translation. See
  [Getting Started](GETTING_STARTED.md), [CLI](CLI.md), and
  [Architecture](ARCHITECTURE.md).
- **Review artifacts** through confidence scoring, structured diagnostics, TODO markers,
  HTML reports, dashboards, and `j2py compare`. See
  [Output Review](OUTPUT_REVIEW.md).
- **Project assessment** with `j2py doctor`, including JSON/HTML reports, SARIF export,
  and conservative config suggestions without live LLM calls. See
  [Doctor](DOCTOR.md) and [SARIF](SARIF.md).
- **Optional LLM completion and review** using configured Anthropic, Gemini, or
  OpenAI-compatible providers, with normal tests and release gates avoiding live LLM
  calls. See [CLI](CLI.md#j2py-translate) and [Output Review](OUTPUT_REVIEW.md).
- **Spring conversion scaffolding** behind explicit opt-in configuration:
  `annotation_map_preset: spring`, `SpringWiringPlugin`, wiring sidecars,
  `j2py-wire generate`, `j2py-wire validate`, and a PetClinic owner-slice smoke gate. See
  [Spring Conversion Guide](SPRING_CONVERSION.md).
- **JPA and JDBC scaffolding** for supported Spring application patterns, including
  SQLAlchemy model output, Spring repository metadata, `JdbcTemplate` SQLAlchemy Core
  scaffolds, simple RowMapper lowering, and JDBC bean topology metadata. See the
  [Spring Mapping Cookbook](examples/SPRING_MAPPING_COOKBOOK.md) and
  [Spring Wiring Metadata](SPRING_WIRING_METADATA.md).

## Evidence Map

The full claim-to-evidence inventory is tracked in
[0.7.0 release test coverage inventory](RELEASE_TEST_EVIDENCE_0.7.0.md).

| Claim | Evidence |
|---|---|
| Core CLI workflow | `j2py --help`, [Getting Started](GETTING_STARTED.md), [CLI](CLI.md) |
| Rule-layer review artifacts | [Output Review](OUTPUT_REVIEW.md), `j2py translate --report`, `j2py dashboard`, `j2py compare` |
| Project assessment | `j2py doctor --json --html`, [Doctor](DOCTOR.md), [SARIF](SARIF.md) |
| Spring sidecars and FastAPI wiring | [Spring Conversion Guide](SPRING_CONVERSION.md), `make test-spring-smoke` |
| Spring/JPA/JDBC mapping scope | [Spring Mapping Cookbook](examples/SPRING_MAPPING_COOKBOOK.md), [Spring Wiring Metadata](SPRING_WIRING_METADATA.md) |
| Release gate | `make release-check`, [Releasing](RELEASING.md) |

## Start Here

Core install:

```bash
pip install --pre j2py-converter
j2py --help
```

Spring/FastAPI/SQLAlchemy trial install:

```bash
pip install --pre "j2py-converter[spring]"
j2py-wire --help
```

First workflow:

1. Read [Getting Started](GETTING_STARTED.md).
2. Run `j2py doctor` on the source tree.
3. Translate with `--no-llm` first.
4. Review generated Python, diagnostics, and reports.
5. Add project config only where the target Python runtime policy is explicit.
6. For Spring slices, follow [Spring Conversion Guide](SPRING_CONVERSION.md).

## Quality Evidence

Release validation is recorded through:

- `make release-check`
- relevant corpus checks or scorecard summaries
- [0.7.0 performance baseline](RELEASE_PERFORMANCE_BASELINE_0.7.0.md)
- package build and clean-environment install smoke; see
  [0.7.0 release candidate checklist](RELEASE_CANDIDATE_EVIDENCE_0.7.0.md)

Do not claim broader runtime support than these gates prove.

## Known Limits

- j2py output remains a reviewable migration scaffold. Production correctness still
  requires project tests and human review.
- Framework behavior is not enabled by default. Spring/FastAPI/SQLAlchemy support requires
  explicit configuration and project-owned runtime wiring.
- JDBC support lowers reviewable call shapes and metadata; it does not provide a native
  JDBC runtime, driver bridge, connection pool, or transaction policy.
- Complex framework behavior remains manual: Spring Security, AOP proxy semantics,
  WebFlux/reactive behavior, full JPA relationship semantics, JPQL, generated keys, batch
  updates, stored procedures, and vendor-specific SQL behavior.
- LLM completion is optional and provider-dependent. Release gates must remain useful
  without live LLM calls.

## Release Tone

Use specific evidence-backed wording. Avoid broad claims such as "automatic Spring
migration", "drop-in runtime", "seamless conversion", or "enterprise-ready" unless a
future release adds evidence for those claims.
