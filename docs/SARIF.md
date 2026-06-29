# j2py SARIF export

`j2py sarif` converts a `j2py doctor` assessment JSON file into SARIF 2.1.0 so migration
diagnostics can be uploaded to GitHub code scanning or archived as CI artifacts.

The exporter is offline and deterministic. It does not call LLM providers, GitHub, or any
network service.

## Usage

First generate a doctor assessment:

```bash
j2py doctor assess src/main/java --json j2py-assessment.json
```

Then export SARIF:

```bash
j2py sarif j2py-assessment.json --output j2py.sarif
```

## Included diagnostics

The current exporter maps doctor assessment findings to stable SARIF rule IDs:

| Rule ID | Source |
|---|---|
| `j2py.parse-error` | Java parse failures |
| `j2py.unhandled-construct` | Rule-layer unhandled diagnostics |
| `j2py.semantic-warning` | Rule-layer semantic warnings |
| `j2py.todo` | Generated TODO/manual-port markers |
| `j2py.validation.syntax` | Python syntax validation failures |
| `j2py.validation.ruff` | Ruff validation failures |
| `j2py.validation.mypy` | Mypy validation failures |
| `j2py.validation` | Validation failures that cannot be classified more specifically |
| `j2py.unresolved-import` | Doctor unresolved import boundary candidates |

Java source diagnostics use Java file locations when doctor has line data. Validation
diagnostics use generated Python locations when the validation message includes them.
Unresolved imports and TODO markers may be file-level results when line data is not
available in the assessment.

## GitHub Actions

Example workflow step:

```yaml
- name: Generate j2py assessment
  run: |
    j2py doctor assess src/main/java --json j2py-assessment.json --include-validation
    j2py sarif j2py-assessment.json --output j2py.sarif

- name: Upload j2py SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: j2py.sarif
```

## Limits

`j2py sarif` currently consumes doctor assessment JSON only. It does not export directly
from `j2py translate` results, and it does not upload to GitHub by itself.
