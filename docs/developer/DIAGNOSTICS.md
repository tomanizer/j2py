# Diagnostics

Use this guide when adding diagnostics, warnings, TODO markers, confidence behavior,
doctor findings, or SARIF output.

Diagnostics are part of j2py's review contract. They tell users what was translated,
what was not translated, and what still needs human attention.

## Sources

| Diagnostic source | Module | Output surface |
|-------------------|--------|----------------|
| Rule-layer handled/unhandled records | `j2py/translate/diagnostics.py` | `TranslationResult.diagnostics`, doctor JSON/HTML |
| Rule-layer semantic warnings | `TranslationDiagnostics.warn(...)` | confidence cap, doctor, SARIF |
| Generated TODO markers | translation modules and runtime TODO sentinel | generated Python, VS Code diagnostics |
| Python validation | `j2py/validate/checks.py` | CLI/API result, doctor, SARIF |
| Structural verification | `j2py/verify/` | CLI/API result, confidence cap |
| Doctor assessment | `j2py/doctor_assessment.py` | `j2py doctor` JSON/HTML/text |
| SARIF export | `j2py/sarif.py` | code-scanning tools |
| Wiring validation | `j2py/wire/validation.py` | `j2py-wire validate` |

## Rule-Layer Records

Use `TranslationDiagnostics.record(...)` when a node is part of rule coverage:

- `supported=True` means the rule layer handled the construct;
- `supported=False` means the construct remains a gap;
- `reason` should be stable enough for reports and hotspot aggregation;
- `category` should be set when it helps grouping;
- `facts` should hold compact machine-readable details.

Use `TranslationDiagnostics.warn(...)` when j2py emits Python but wants review. Warnings
do not reduce raw coverage, but they do affect surfaced confidence.

## Confidence

User-facing confidence is computed in `j2py/pipeline.py` from:

- rule coverage;
- semantic warning count;
- validation result;
- structural verification result.

The current policy is:

- raw rule coverage starts from handled / total rule-layer records;
- semantic warnings cap confidence below perfect;
- syntactically invalid Python has zero confidence;
- ruff, mypy, or structural failures cap confidence at review-required level.

Do not change confidence behavior casually. If the policy changes, update:

- `docs/OUTPUT_REVIEW.md`;
- `docs/API_REFERENCE.md`;
- release-facing docs if a release claim changes;
- tests that assert confidence behavior.

## TODO Markers

Use `TODO(j2py)` for visible manual migration points in generated Python. Keep wording
specific enough that a user knows what to replace. Avoid vague messages such as
"unsupported" when the tool can name the missing policy.

Good TODOs include:

- what Java construct caused the boundary;
- what Python owner must supply;
- whether the issue is framework policy, runtime policy, or unsupported syntax.

The VS Code extension currently detects `TODO(j2py)` and `__j2py_todo__`, so keep those
markers stable unless the extension is updated in the same change.

## Doctor And SARIF

Doctor reports should aggregate diagnostics without hiding source facts. If adding a new
diagnostic family, check whether it should appear in:

- file-level translation payloads in `j2py/doctor_assessment.py`;
- hotspot summaries;
- config suggestions;
- doctor diff output;
- SARIF rules in `j2py/sarif.py`.

SARIF rule IDs should be stable and namespaced under `j2py.*`. Use specific IDs when a
tool can act differently on the result, such as `j2py.validation.syntax` versus
`j2py.validation.mypy`.

## Tests

For translation diagnostics:

```bash
pytest tests/translate -q
```

For confidence, validation, doctor, and SARIF:

```bash
pytest tests/test_pipeline.py tests/validate tests/test_doctor.py tests/test_sarif.py -q
```

For release-facing diagnostic wording:

```bash
pytest tests/test_release_diagnostics_todo_audit.py -q
```

For wiring diagnostics:

```bash
pytest tests/wire -q
```

## Review Checklist

- Reasons and codes are stable enough for reports.
- A warning is not used to hide an unsupported construct.
- Confidence changes are documented and tested.
- TODO wording tells users what to do next.
- Doctor and SARIF surfaces are considered when diagnostics become user-facing.
