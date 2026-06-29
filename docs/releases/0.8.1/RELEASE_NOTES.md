# j2py 0.8.1 Release Notes

0.8.1 is a patch beta release after 0.8.0. It keeps the same product boundary:
j2py translates Java source into reviewable Python, records deterministic evidence, and
uses explicit sidecars for optional application wiring. It does not become a JVM,
Spring container, JDBC bridge, Hibernate runtime, or automatic full-application migration
tool.

## Headline

j2py 0.8.1 ships post-0.8.0 correctness fixes for nested class literals, `EnumSet`,
WordUtils delimiter handling, Predicate and method-reference lowering, and code-point
case conversion. It also expands the external case-study evidence with the scoped
java-semver `Version` core loop and Commons Text WordUtils/CaseUtils coverage, while
preserving the release-tested package and wiring boundaries from 0.8.0.

## What Users Get

- **More accurate JDK and library lowering** for `EnumSet` factory methods,
  `Math.incrementExact` diagnostics, `Predicate.test(...)`, collection
  `::contains` method references, `Character.toLowerCase(codePoint)`, and forwarded
  null varargs defaults. See [Getting Started](../../GETTING_STARTED.md),
  [CLI](../../CLI.md), and [Architecture](../../ARCHITECTURE.md).
- **Nested class-literal fixes** so file-declared nested types referenced from method
  bodies emit enclosing-qualified names such as `Outer.Color` instead of undefined bare
  names.
- **Expanded external case-study evidence**: the java-semver case study now includes the
  seven-file `Version` / parser core loop with zero residual translator-defect patches,
  and Commons Text WordUtils joins the Commons Text case-study track. See
  [java-semver](../../CASE_STUDY_JSEMVER.md) and
  [Commons Text CaseUtils](../../CASE_STUDY_COMMONS_TEXT_CASEUTILS.md).
- **Implementation hygiene in wiring targets** through shared helper logic for existing
  `j2py-wire` target generators. The generated wiring contract is intentionally
  unchanged; the refactor reduces duplicated internal paths.

## Evidence Map

The full claim-to-evidence inventory is tracked in
`docs/releases/0.8.1/TEST_EVIDENCE.md`
([0.8.1 release test coverage inventory](TEST_EVIDENCE.md)).

| Claim | Evidence |
|---|---|
| Core CLI workflow | `j2py --help`, [Getting Started](../../GETTING_STARTED.md), [CLI](../../CLI.md) |
| Rule-layer review artifacts | [Output Review](../../OUTPUT_REVIEW.md), `j2py translate --report`, `j2py dashboard`, `j2py compare` |
| Project assessment | `j2py doctor --json --html`, [Doctor](../../DOCTOR.md), [SARIF](../../SARIF.md) |
| Spring sidecars and FastAPI wiring | [Spring Conversion Guide](../../SPRING_CONVERSION.md), `make test-spring-smoke` |
| Additional wiring targets | [Wiring](../../WIRING.md), [Wiring targets](../../developer/WIRING_TARGETS.md), `tests/wire/` |
| External case studies | [java-semver](../../CASE_STUDY_JSEMVER.md), [Commons Text CaseUtils](../../CASE_STUDY_COMMONS_TEXT_CASEUTILS.md), [Commons Codec Hex](../../CASE_STUDY_COMMONS_CODEC_HEX.md) |
| Release gate | `make release-check`, [Releasing](../../RELEASING.md) |

## Start Here

Core install:

```bash
pip install j2py-converter
j2py --help
```

Spring/FastAPI/SQLAlchemy trial install:

```bash
pip install "j2py-converter[spring]"
j2py-wire --help
```

First workflow:

1. Read [Getting Started](../../GETTING_STARTED.md).
2. Run `j2py doctor` on the source tree.
3. Translate with `--no-llm` first.
4. Review generated Python, diagnostics, and reports.
5. Add project config only where the target Python runtime policy is explicit.
6. For Spring slices, follow [Spring Conversion Guide](../../SPRING_CONVERSION.md).

## Quality Evidence

Release validation is recorded through:

- `make release-check`
- focused release-record and documentation tests
- case-study and equivalence fixtures that run in the normal release gate
- `docs/releases/0.8.1/PERFORMANCE_BASELINE.md`
  ([0.8.1 performance baseline](PERFORMANCE_BASELINE.md))
- package build and clean-environment install smoke; see
  `docs/releases/0.8.1/CANDIDATE_EVIDENCE.md`
  ([0.8.1 release candidate checklist](CANDIDATE_EVIDENCE.md))

Do not claim broader runtime support than these gates prove.

## Known Limits

- j2py output remains a reviewable migration scaffold. Production correctness still
  requires project tests and human review.
- Framework behavior is not enabled by default. Spring/FastAPI/SQLAlchemy support
  requires explicit configuration and project-owned runtime wiring.
- `j2py-wire` emits scaffolding and validation findings; it does not own sessions,
  credentials, auth, transactions, migrations, deployment, or persistence policy.
- JDBC support lowers reviewable call shapes and metadata; it does not provide a native
  JDBC runtime, driver bridge, connection pool, or transaction policy.
- Complex framework behavior remains manual: Spring Security, AOP proxy semantics,
  WebFlux/reactive behavior, full JPA relationship semantics, JPQL, generated keys,
  batch updates, stored procedures, and vendor-specific SQL behavior.
- LLM completion is optional and provider-dependent. Release gates remain useful without
  live LLM calls.

## Release Tone

Use specific evidence-backed wording. Avoid broad claims such as "automatic Spring
migration", "drop-in runtime", "seamless conversion", or "enterprise-ready" unless a
future release adds evidence for those claims.
