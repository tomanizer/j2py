"""Record LLM repairs as transparent backlog for future rule-layer work."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from j2py.llm.env import enabled_env_flag
from j2py.llm.prompts import PROMPT_VERSION
from j2py.translate.diagnostics import TranslationDiagnostics, diagnostic_payload
from j2py.validate.checks import ValidationResult
from j2py.verify.structure import StructuralVerificationResult

SCHEMA_VERSION = "1"
DEFAULT_HARVEST_DIR = Path(".j2py") / "harvest"
RECORDS_FILE_NAME = "records.jsonl"
MAX_DIFF_CHARS = 12_000

_PROTOCOL_CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(\s*Protocol\b", re.MULTILINE)
_TODO_LINE_RE = re.compile(r"TODO\(j2py\)|__j2py_todo__")


@dataclass(frozen=True)
class LlmHarvestTrigger:
    kinds: tuple[str, ...]
    coverage: float
    unhandled: tuple[dict[str, object], ...]
    pre_validation_errors: tuple[str, ...]
    structural_errors: tuple[str, ...]


@dataclass(frozen=True)
class LlmHarvestRecord:
    schema_version: str
    recorded_at: str
    source_path: str
    java_sha256: str
    model: str
    prompt_version: str
    trigger: LlmHarvestTrigger
    repair_signals: tuple[str, ...]
    final_todos: tuple[str, ...]
    diff_excerpt: str
    status: str = "open"
    notes: str = ""


def llm_harvest_enabled() -> bool:
    return enabled_env_flag("J2PY_LLM_HARVEST")


def harvest_records_path(*, repo_root: Path | None = None) -> Path:
    root = repo_root or Path.cwd()
    override = os.environ.get("J2PY_LLM_HARVEST_PATH", "").strip()
    if override:
        return Path(override)
    return root / DEFAULT_HARVEST_DIR / RECORDS_FILE_NAME


def load_harvest_records(path: Path | None = None) -> list[dict[str, object]]:
    """Load all harvest records from jsonl."""
    records_path = path or harvest_records_path()
    if not records_path.is_file():
        return []
    records: list[dict[str, object]] = []
    for line in records_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def latest_harvest_records(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep the newest record per ``source_path`` (append order wins on ties)."""
    by_path: dict[str, dict[str, object]] = {}
    for record in records:
        source = str(record.get("source_path", ""))
        if source:
            by_path[source] = record
    return list(by_path.values())


def write_harvest_records(
    records: list[dict[str, object]],
    path: Path | None = None,
) -> Path:
    """Overwrite the harvest jsonl with the given records."""
    records_path = path or harvest_records_path()
    records_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True) for record in records]
    records_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return records_path


def compact_harvest_records(
    path: Path | None = None,
    *,
    drop_resolved: bool = True,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Prune duplicate source paths; optionally drop ``status=resolved`` rows.

    Returns ``(records_before, records_after)``.
    """
    records_path = path or harvest_records_path()
    records = load_harvest_records(records_path)
    before = len(records)
    if drop_resolved:
        records = [record for record in records if record.get("status") != "resolved"]
    compacted = latest_harvest_records(records)
    after = len(compacted)
    if not dry_run and after != before:
        write_harvest_records(compacted, records_path)
    return before, after


def infer_repair_signals(*, skeleton: str, final: str) -> tuple[str, ...]:
    """Assign transparent tags from skeleton vs final output."""
    signals: list[str] = []

    def add(tag: str, condition: bool) -> None:
        if condition and tag not in signals:
            signals.append(tag)

    add("overload-dispatch", "typing.overload" in final and "typing.overload" not in skeleton)
    add(
        "overload-runtime-to-typing",
        "@overloaded" in skeleton and "typing.overload" in final,
    )
    add(
        "protocol-stub",
        final.count("Protocol[") > skeleton.count("Protocol[")
        or len(_protocol_names(final)) > len(_protocol_names(skeleton)),
    )
    add("generic-typevar", "TypeVar(" in final and "TypeVar(" not in skeleton)
    add(
        "todo-placeholder-removed",
        "__j2py_todo__" in skeleton and "__j2py_todo__" not in final,
    )
    add(
        "unsupported-stmt-removed",
        "TODO(j2py): unsupported" in skeleton and "TODO(j2py): unsupported" not in final,
    )
    add("runtime-not-implemented-stub", "NotImplementedError" in final)
    add(
        "adapter-class-introduced",
        bool(re.search(r"^class _\w+", final, re.MULTILINE))
        and not re.search(r"^class _\w+", skeleton, re.MULTILINE),
    )
    add(
        "anonymous-class-retained",
        "_J2pyAnonymous" in skeleton or "_J2pyAnonymous" in final,
    )
    add(
        "jdk-import-removed",
        _bad_java_import_lines(skeleton) > _bad_java_import_lines(final),
    )

    return tuple(signals)


def build_harvest_record(
    *,
    source_path: Path,
    java_source: str,
    skeleton: str,
    final_python: str,
    model: str,
    coverage: float,
    diagnostics: TranslationDiagnostics,
    pre_validation: ValidationResult | None,
    structural_verification: StructuralVerificationResult | None,
) -> LlmHarvestRecord:
    trigger = _build_trigger(
        coverage=coverage,
        diagnostics=diagnostics,
        pre_validation=pre_validation,
        structural_verification=structural_verification,
    )
    return LlmHarvestRecord(
        schema_version=SCHEMA_VERSION,
        recorded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        source_path=str(source_path),
        java_sha256=hashlib.sha256(java_source.encode()).hexdigest(),
        model=model,
        prompt_version=PROMPT_VERSION,
        trigger=trigger,
        repair_signals=infer_repair_signals(skeleton=skeleton, final=final_python),
        final_todos=_extract_todos(final_python),
        diff_excerpt=_diff_excerpt(skeleton, final_python, source_path.name),
    )


def append_harvest_record(record: LlmHarvestRecord, *, repo_root: Path | None = None) -> Path:
    path = harvest_records_path(repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _record_to_json(record)
    existing = load_harvest_records(path)
    latest = latest_harvest_records(existing)
    prior = next((item for item in latest if item.get("source_path") == record.source_path), None)
    if (
        prior is not None
        and prior.get("java_sha256") == record.java_sha256
        and prior.get("repair_signals") == list(record.repair_signals)
    ):
        return path
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
    return path


def record_llm_repair(
    *,
    source_path: Path,
    java_source: str,
    skeleton: str,
    final_python: str,
    model: str,
    coverage: float,
    diagnostics: TranslationDiagnostics,
    pre_validation: ValidationResult | None,
    structural_verification: StructuralVerificationResult | None,
    repo_root: Path | None = None,
) -> Path | None:
    if not llm_harvest_enabled():
        return None
    record = build_harvest_record(
        source_path=source_path,
        java_source=java_source,
        skeleton=skeleton,
        final_python=final_python,
        model=model,
        coverage=coverage,
        diagnostics=diagnostics,
        pre_validation=pre_validation,
        structural_verification=structural_verification,
    )
    return append_harvest_record(record, repo_root=repo_root)


def _build_trigger(
    *,
    coverage: float,
    diagnostics: TranslationDiagnostics,
    pre_validation: ValidationResult | None,
    structural_verification: StructuralVerificationResult | None,
) -> LlmHarvestTrigger:
    kinds: list[str] = []
    if coverage < 1.0:
        kinds.append("coverage_gap")
    if pre_validation is not None:
        if not pre_validation.syntax_ok:
            kinds.append("syntax_repair")
        if not pre_validation.mypy_ok:
            kinds.append("mypy_repair")
    if structural_verification is not None and not structural_verification.ok:
        kinds.append("structural_repair")
    if not kinds:
        kinds.append("unknown")
    return LlmHarvestTrigger(
        kinds=tuple(kinds),
        coverage=coverage,
        unhandled=tuple(diagnostic_payload(item) for item in diagnostics.unhandled),
        pre_validation_errors=_pre_validation_errors(pre_validation),
        structural_errors=tuple(structural_verification.errors)
        if structural_verification is not None
        else (),
    )


def _pre_validation_errors(pre_validation: ValidationResult | None) -> tuple[str, ...]:
    if pre_validation is None:
        return ()
    return tuple(pre_validation.syntax_errors + pre_validation.mypy_errors)


def _extract_todos(source: str) -> tuple[str, ...]:
    todos: list[str] = []
    for line in source.splitlines():
        if _TODO_LINE_RE.search(line):
            todos.append(line.strip())
    return tuple(todos)


def _diff_excerpt(before: str, after: str, label: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"{label} (skeleton)",
        tofile=f"{label} (llm)",
        lineterm="",
    )
    text = "\n".join(diff)
    if len(text) <= MAX_DIFF_CHARS:
        return text
    return text[:MAX_DIFF_CHARS] + "\n... diff truncated ..."


def _protocol_names(source: str) -> set[str]:
    return set(_PROTOCOL_CLASS_RE.findall(source))


def _bad_java_import_lines(source: str) -> int:
    return sum(
        1
        for line in source.splitlines()
        if line.startswith("from ") and re.search(r"\.(Integer|String|ObjectName)\b", line)
    )


def _record_to_json(record: LlmHarvestRecord) -> dict[str, object]:
    return asdict(record)
