# Python API Reference

This page records the supported Python import surface. Prefer these APIs for scripts,
test harnesses, and migration automation. Lower-level modules under `j2py.translate`,
`j2py.parse`, `j2py.analyze`, and most `j2py.cli` modules are implementation details
unless you are contributing to j2py itself.

For worked examples, start with the [Python API Guide](API.md).

## Stability Levels

| Level | Meaning |
|-------|---------|
| Public | Intended for programmatic use; changes should be deliberate and documented. |
| Public facade | Stable import path over internal modules; behavior/schema stability matters more than implementation location. |
| Experimental | Available for advanced users, but the contract may change as the feature matures. |
| Internal | Do not depend on this outside j2py development. |

## Translation Pipeline

Module: `j2py.pipeline`

Stability: Public.

### `translate_file`

```python
def translate_file(
    path: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str | None = None,
    llm_provider: Literal["anthropic", "gemini", "openai"] | None = None,
    llm_review: bool = False,
    llm_review_scope: Literal["all", "warnings", "low-confidence"] = "all",
    validate: bool = True,
) -> TranslationResult
```

Runs one Java file through parse, symbol extraction, deterministic translation, optional
LLM completion/review, validation, and confidence scoring.

### `translate_directory`

```python
def translate_directory(
    source_root: Path,
    output_root: Path,
    *,
    cfg: TranslationConfig,
    use_llm: bool = True,
    model: str | None = None,
    llm_provider: Literal["anthropic", "gemini", "openai"] | None = None,
    llm_review: bool = False,
    llm_review_scope: Literal["all", "warnings", "low-confidence"] = "all",
    validate: bool = True,
    workers: int | None = None,
    llm_concurrency: int | None = None,
    incremental: bool = False,
) -> DirectoryTranslationResult
```

Translates all `*.java` files under `source_root`, computes package-relative output paths,
uses dependency order where possible, and optionally skips unchanged files.

### `TranslationResult`

```python
@dataclass
class TranslationResult:
    source_path: Path
    python_source: str
    used_llm: bool = False
    confidence: float = 1.0
    parse_ok: bool = True
    output_path: Path | None = None
    diagnostics: TranslationDiagnostics | None = None
    validation: ValidationResult | None = None
    structural_verification: StructuralVerificationResult | None = None
    llm_review_ran: bool = False
    llm_review_findings: list[LlmReviewFinding] = field(default_factory=list)
    llm_review_error: str | None = None
    skipped: bool = False
```

`confidence` is a review signal, not proof of semantic equivalence. Use diagnostics,
validation, reports, and equivalence tests for evidence.

### `DirectoryTranslationResult`

```python
@dataclass
class DirectoryTranslationResult:
    source_root: Path
    output_root: Path
    files: list[TranslationResult]
    order: list[Path]
    warnings: list[str]
    skipped_count: int = 0
    translated_count: int = 0
```

### Wiring Sidecar Helpers

```python
def wiring_metadata_sidecar_path(output_path: Path) -> Path
def wiring_metadata_payload(result: TranslationResult) -> dict[str, object] | None
def write_wiring_metadata_sidecar(result: TranslationResult) -> Path | None
```

These helpers serialize framework metadata emitted during translation. j2py writes that
metadata to sidecars. `j2py-wire` uses sidecars to generate target-stack wiring.

## Configuration

Module: `j2py.config.loader`

Stability: Public.

### `TranslationConfig`

`TranslationConfig` is a Pydantic model containing the effective translation policy.

Important fields:

| Field | Type |
|-------|------|
| `type_map` | `dict[str, str]` |
| `collection_map` | `dict[str, str]` |
| `exception_map` | `dict[str, str]` |
| `literal_map` | `dict[str, str]` |
| `import_map` | `dict[str, str]` |
| `annotation_map_preset` | `"spring" | None` |
| `annotation_map` | `dict[str, AnnotationMapEntry]` |
| `member_map` | `dict[str, MemberMapEntry]` |
| `framework_plugins` | `list[FrameworkPlugin]` |
| `emit_wiring_metadata` | `bool` |
| `workers` | `int` |
| `llm_concurrency` | `int` |
| `llm_provider` | `"anthropic" | "gemini" | "openai" | None` |
| `llm_base_url` | `str | None` |
| `model` | `str | None` |

```python
cfg = TranslationConfig.default()
```

### `ConfigLoader`

```python
class ConfigLoader:
    def add_defaults(self) -> ConfigLoader: ...
    def add_auto_discovered(self, root: Path) -> ConfigLoader: ...
    def add_file(self, path: Path) -> ConfigLoader: ...
    def add_mapping(
        self,
        overrides: dict[str, Any],
        *,
        source: Path = Path("<config mapping>"),
    ) -> ConfigLoader: ...
    def build(self) -> TranslationConfig: ...
```

Layering rules: later scalar values replace earlier values; dictionaries merge with later
keys overriding earlier keys; set-like values union when the prior value is a set.

### Config Models And Errors

```python
class ConfigError(ValueError): ...
class AnnotationMapEntry(BaseModel): ...
class MemberMapEntry(BaseModel): ...
```

Use [Configuration](CONFIGURATION.md) for the full schema and examples.

## Diagnostics And Validation

Modules: `j2py.translate.diagnostics`, `j2py.validate.checks`

Stability: Public through result objects; direct imports are supported for inspection and
test harnesses.

### `ValidationResult`

```python
@dataclass
class ValidationResult:
    path: Path
    syntax_ok: bool = False
    mypy_ok: bool = False
    ruff_ok: bool = False
    syntax_errors: list[str] = field(default_factory=list)
    mypy_errors: list[str] = field(default_factory=list)
    ruff_errors: list[str] = field(default_factory=list)
    ruff_available: bool = True
    mypy_available: bool = True

    @property
    def ok(self) -> bool: ...

    @property
    def skipped_checks(self) -> list[str]: ...
```

```python
def validate_source(source: str, path: Path | None = None) -> ValidationResult
def validate_file(path: Path) -> ValidationResult
def validate_directory(files: dict[Path, str]) -> dict[Path, ValidationResult]
```

Missing `ruff` or `mypy` is reported through `skipped_checks`; missing tools are not
treated as translation failures.

### `TranslationDiagnostics`

`TranslationResult.diagnostics` is the normal access point. Useful members include:

| Member | Meaning |
|--------|---------|
| `coverage` / `rule_coverage` | Rule-layer handled-node ratio. |
| `semantic_warning_count` | Count of review-required semantic warnings. |
| `handled` | Handled node diagnostics. |
| `unhandled` | Unsupported or ambiguous constructs. |
| `warnings` | Semantic warnings. |
| `imports` | Imports required by emitted Python constructs. |
| `framework_metadata` | Framework metadata records for sidecars. |

## Reports

Module: `j2py.report`

Stability: Public, with the CLI remaining the preferred stable interface for reports.

```python
def write_translation_report(
    path: Path,
    results: list[TranslationResult],
    *,
    title: str = "j2py translation report",
) -> None

def write_dashboard_for_results(
    path: Path,
    results: list[TranslationResult],
    *,
    source_root: Path,
    output_root: Path,
    title: str = "j2py translation dashboard",
) -> None

def write_dashboard_from_state(
    output_root: Path,
    dashboard_path: Path,
    *,
    title: str = "j2py translation dashboard",
) -> None
```

## Doctor Assessment

Module: `j2py.doctor`

Stability: Public facade.

```python
DOCTOR_SCHEMA_VERSION: int
DOCTOR_GATE_SCHEMA_VERSION: int
DOCTOR_GATE_PROFILES: tuple[str, ...]

@dataclass(frozen=True)
class DoctorAssessment:
    payload: dict[str, Any]
    def to_json(self) -> str: ...

@dataclass(frozen=True)
class DoctorDiff:
    payload: dict[str, Any]
    def to_json(self) -> str: ...

@dataclass(frozen=True)
class DoctorGateResult:
    payload: dict[str, Any]
    def to_json(self) -> str: ...

@dataclass(frozen=True)
class DoctorGateThresholds:
    max_parse_failures: int | None = None
    min_average_coverage: float | None = None
    min_file_coverage: float | None = None
    max_files_below_coverage: int | None = None
    ...
```

```python
def assess_project(
    source: Path,
    *,
    cfg: TranslationConfig,
    include_validation: bool = False,
    sample_limit: int | None = None,
) -> DoctorAssessment

def diff_assessments(before: DoctorAssessment, after: DoctorAssessment) -> DoctorDiff
def doctor_gate_thresholds_for_profile(profile: str) -> DoctorGateThresholds
def evaluate_doctor_gate(
    assessment: DoctorAssessment,
    *,
    profile: str,
    thresholds: DoctorGateThresholds | None = None,
    sample_limit: int | None = None,
) -> DoctorGateResult
def load_assessment_json(path: Path) -> DoctorAssessment
def write_assessment_json(path: Path, assessment: DoctorAssessment) -> None
def write_assessment_html(path: Path, assessment: DoctorAssessment) -> None
def write_config_suggestions(path: Path, assessment: DoctorAssessment) -> None
def write_doctor_diff_json(path: Path, diff: DoctorDiff) -> None
def write_doctor_gate_json(path: Path, result: DoctorGateResult) -> None
def render_assessment_html(assessment: DoctorAssessment) -> str
def render_config_suggestions(assessment: DoctorAssessment) -> str
def render_doctor_diff_text(diff: DoctorDiff) -> str
def render_doctor_gate_text(result: DoctorGateResult) -> str
```

Use [Doctor](DOCTOR.md) and [SARIF](SARIF.md) for output
schema interpretation and workflows.

## SARIF

Module: `j2py.sarif`

Stability: Public.

```python
SARIF_VERSION = "2.1.0"

@dataclass(frozen=True)
class SarifReport:
    payload: dict[str, Any]
    def to_json(self) -> str: ...

def load_sarif_assessment(path: Path) -> DoctorAssessment
def assessment_to_sarif(assessment: DoctorAssessment) -> SarifReport
def write_sarif(path: Path, report: SarifReport) -> None
```

## Framework Plugins

Module: `j2py.framework`

Stability: Public plugin contract.

```python
@dataclass(frozen=True)
class InitParam:
    py_name: str
    py_type: str

@dataclass(frozen=True)
class FrameworkAnnotation:
    name: str
    simple_name: str
    values: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

@dataclass(frozen=True)
class FrameworkParam:
    java_name: str
    py_name: str
    java_type: str
    py_type: str

@dataclass(frozen=True)
class FrameworkTransformResult:
    prefix_lines: tuple[str, ...] = ()
    base_classes: tuple[str, ...] = ()
    init_params: tuple[InitParam, ...] = ()
    imports: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    handled: bool = False

@dataclass
class FrameworkContext:
    node: JavaNode
    element_kind: str
    element_name: str
    java_name: str
    py_name: str
    annotations: tuple[FrameworkAnnotation, ...]
    diagnostics: TranslationDiagnostics
    java_type: str | None = None
    py_type: str | None = None
    parameters: tuple[FrameworkParam, ...] = ()

@dataclass(frozen=True)
class FrameworkMetadataRecord:
    plugin: str
    kind: str
    java_name: str
    python_name: str
    annotations: tuple[FrameworkAnnotation, ...]
    metadata: Mapping[str, object]
```

```python
class FrameworkPlugin(ABC):
    name: str = "unnamed"

    def transform_class(self, ctx: FrameworkContext) -> FrameworkTransformResult: ...
    def transform_field(self, ctx: FrameworkContext) -> FrameworkTransformResult: ...
    def transform_method(self, ctx: FrameworkContext) -> FrameworkTransformResult: ...
```

Use [Framework plugins](FRAMEWORK_PLUGINS.md) for authoring guidance.

## Wiring Sidecars

Module: `j2py.wire`

Stability: Experimental public API. The sidecar schema is intentionally generic, but
target generators are still evolving.

```python
class WiringElement(BaseModel):
    plugin: str
    kind: Literal["class", "field", "method", "constructor"]
    java_name: str
    python_name: str
    annotations: list[dict[str, object]]
    metadata: dict[str, object]

    @property
    def spring(self) -> dict[str, object]: ...

class WiringSidecar(BaseModel):
    schema_version: int
    source: str
    output: str
    elements: list[WiringElement]

    def python_module(self, translated_root: Path) -> str: ...
```

```python
@dataclass(frozen=True)
class WiringLoadDiagnostic:
    path: Path
    level: Literal["warning", "error"]
    message: str

@dataclass(frozen=True)
class WiringLoadResult:
    sidecars: list[WiringSidecar]
    diagnostics: list[WiringLoadDiagnostic]

    @property
    def has_errors(self) -> bool: ...

def discover_wiring_sidecars(translated_root: Path) -> list[Path]
def load_wiring_sidecar(path: Path) -> tuple[WiringSidecar | None, list[WiringLoadDiagnostic]]
def load_wiring_sidecars(translated_root: Path) -> WiringLoadResult
```

Use [Wiring](WIRING.md) for the CLI workflow and target generation behavior.

## Internal Surfaces

These modules are important to contributors but are not general public API:

- `j2py.parse.*`
- `j2py.analyze.*`
- `j2py.translate.*`
- `j2py.llm.*`
- `j2py.verify.*`
- `j2py.cli.*`

Use them directly only when changing j2py internals, and follow
[Contributing](../CONTRIBUTING.md) plus the developer task map in the
[documentation index](README.md#developer-docs).
