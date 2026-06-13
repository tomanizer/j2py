"""Persistent translation state for incremental runs and dashboards."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from j2py.pipeline import TranslationResult

STATE_FILE_NAME = ".j2py-state.json"
STATE_VERSION = "0.3.0"


@dataclass(frozen=True)
class StateEntry:
    source_path: str
    output_path: str
    sha256: str
    translated_at: str
    confidence: float
    used_llm: bool
    validation_ok: bool | None
    syntax_ok: bool | None
    mypy_ok: bool | None
    ruff_ok: bool | None
    todo_count: int
    unhandled_count: int
    loc: int


def state_path(output_root: Path) -> Path:
    return output_root / STATE_FILE_NAME


def source_key(path: Path, source_root: Path) -> str:
    try:
        return str(path.relative_to(source_root))
    except ValueError:
        return str(path)


def output_key(path: Path, output_root: Path) -> str:
    try:
        return str(path.relative_to(output_root))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(output_root: Path) -> dict[str, StateEntry]:
    path = state_path(output_root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    files = payload.get("files", {})
    if not isinstance(files, dict):
        return {}
    entries: dict[str, StateEntry] = {}
    for key, raw in files.items():
        if isinstance(raw, dict):
            entries[str(key)] = StateEntry(
                source_path=str(raw.get("source_path", key)),
                output_path=str(raw.get("output_path", "")),
                sha256=str(raw.get("sha256", "")),
                translated_at=str(raw.get("translated_at", "")),
                confidence=float(raw.get("confidence", 0.0)),
                used_llm=bool(raw.get("used_llm", False)),
                validation_ok=_optional_bool(raw.get("validation_ok")),
                syntax_ok=_optional_bool(raw.get("syntax_ok")),
                mypy_ok=_optional_bool(raw.get("mypy_ok")),
                ruff_ok=_optional_bool(raw.get("ruff_ok")),
                todo_count=int(raw.get("todo_count", 0)),
                unhandled_count=int(raw.get("unhandled_count", 0)),
                loc=int(raw.get("loc", 0)),
            )
    return entries


def save_state(output_root: Path, entries: dict[str, StateEntry]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": STATE_VERSION,
        "files": {key: _entry_to_json(entry) for key, entry in sorted(entries.items())},
    }
    state_path(output_root).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def entry_from_result(
    result: TranslationResult,
    *,
    source_root: Path,
    output_root: Path,
) -> StateEntry:
    validation = result.validation
    output = result.output_path or result.source_path.with_suffix(".py")
    return StateEntry(
        source_path=source_key(result.source_path, source_root),
        output_path=output_key(output, output_root),
        sha256=sha256_file(result.source_path),
        translated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        confidence=result.confidence,
        used_llm=result.used_llm,
        validation_ok=validation.ok if validation is not None else None,
        syntax_ok=validation.syntax_ok if validation is not None else None,
        mypy_ok=validation.mypy_ok if validation is not None else None,
        ruff_ok=validation.ruff_ok if validation is not None else None,
        todo_count=_todo_count(result.python_source),
        unhandled_count=(
            len(result.diagnostics.unhandled) if result.diagnostics is not None else 0
        ),
        loc=len(result.source_path.read_text().splitlines()),
    )


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _entry_to_json(entry: StateEntry) -> dict[str, object]:
    return {
        "source_path": entry.source_path,
        "output_path": entry.output_path,
        "sha256": entry.sha256,
        "translated_at": entry.translated_at,
        "confidence": entry.confidence,
        "used_llm": entry.used_llm,
        "validation_ok": entry.validation_ok,
        "syntax_ok": entry.syntax_ok,
        "mypy_ok": entry.mypy_ok,
        "ruff_ok": entry.ruff_ok,
        "todo_count": entry.todo_count,
        "unhandled_count": entry.unhandled_count,
        "loc": entry.loc,
    }


def _todo_count(source: str) -> int:
    return source.count("TODO(j2py)") + source.count("__j2py_todo__")
